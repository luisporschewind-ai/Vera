"""Runtime model loop and tool-dispatch flow."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.streaming import RuntimeOutput, StreamFrame, StreamFrameType
from vera.contracts.tool_actions import ToolEffect
from vera.models.base import ModelMessage, ModelRequest, ModelToolCall, ModelTurn
from vera.models.errors import ModelErrorCode, ModelProviderError, safe_error_payload
from vera.models.streaming import ModelStreamCompleted, ModelTextDelta
from vera.recovery.models import PersistedToolAction
from vera.runtime.approval import ApprovalKind
from vera.runtime.context import RunContext, compact_run_messages, message_bytes
from vera.runtime.flow_protocols import LoopFlowHost
from vera.runtime.intake import (
    _CLAIMED_CHANGESET_NUDGE,
    _EMPTY_AFTER_TOOLS_NUDGE,
    _TOOL_LIMIT_SKIPPED,
    _TOOL_LIMIT_WRAP_UP,
    claims_unissued_changeset,
    tool_call_target,
)
from vera.runtime.read_progress import READ_ONLY_TOOLS
from vera.runtime.state import RunState
from vera.tools.executor import ToolPreparationError


def execute_tool(
    host: LoopFlowHost, context: RunContext, call: ModelToolCall
) -> Iterator[EventEnvelope]:
    signature = f"{call.name}:{call.arguments}"
    if context.last_tool_signature == signature:
        context.repeated_tool_streak += 1
    else:
        context.last_tool_signature = signature
        context.repeated_tool_streak = 1
    if context.repeated_tool_streak >= 3 and call.name not in READ_ONLY_TOOLS:
        yield from host._fail(context, "repeated_tool_call")
        return
    started: dict[str, Any] = {"name": call.name, "call_id": call.call_id}
    target = tool_call_target(call)
    if target:
        started["target"] = target
    yield host._event(context, "tool.started", started)
    if call.parse_error:
        yield from host._reject_tool(
            context,
            call,
            {
                "error": call.parse_error,
                "reason_code": call.parse_error,
                "suggestion": "resend the tool call as a single complete JSON object",
            },
        )
        return
    if call.name == "propose_changeset":
        yield from host._propose(context, call)
        return
    executor = host._tool_executor(context)
    try:
        prepared = executor.prepare(run_id=context.run_id, name=call.name, arguments=call.arguments)
    except ToolPreparationError as exc:
        yield from host._reject_tool(
            context, call, {"error": exc.error_code, "reason_code": exc.error_code}
        )
        return
    yield host._event(
        context,
        "tool.policy_decided",
        {
            "action_id": prepared.action.action_id,
            "name": prepared.action.tool_name,
            "decision": prepared.policy_decision.decision.value,
            "policy_hash": prepared.policy_decision.policy_hash,
        },
    )
    yield host._event(
        context,
        "tool.action_prepared",
        {
            "action_id": prepared.action.action_id,
            "input_hash": prepared.action.input_hash,
            "target_facts_hash": prepared.target_facts_hash,
            "name": prepared.action.tool_name,
        },
    )
    if prepared.policy_decision.decision.value == "approval_required":
        context.pending_tool_action = PersistedToolAction(
            call_id=call.call_id,
            action=prepared.action,
            definition=prepared.definition,
            policy_decision=prepared.policy_decision,
            target_facts_hash=prepared.target_facts_hash,
        )
        context.machine.transition(RunState.AWAITING_APPROVAL)
        request = context.approval_gate.require(
            ApprovalKind.TOOL,
            prepared.action.action_id,
            prepared.action.input_hash,
            executor.approval_description(prepared),
            "high",
            workspace_identity=prepared.action.workspace_identity,
            policy_hash=prepared.policy_decision.policy_hash,
            fact_hash=prepared.target_facts_hash,
            available_scopes=host._available_tool_scopes(prepared),
            required_capabilities=(
                ("apple_ios_build_services",)
                if ToolEffect.APPLE_IOS_BUILD_SERVICES in prepared.action.effects
                else ()
            ),
            **host._security_approval_kwargs(context),
        )
        yield host._stable_event(
            context,
            "approval.required",
            host._approval_payload(request, context),
            RecoveryStage.AWAITING_TOOL_APPROVAL,
        )
        return
    _result, tool_events = host._execute_prepared_tool(context, call, executor, prepared)
    yield from tool_events
    if context.unchanged_read_streak >= 8:
        yield from host._fail(context, "read_loop_no_progress")


def complete_with_retry(
    host: LoopFlowHost, context: RunContext, request: ModelRequest
) -> Iterator[EventEnvelope | StreamFrame | ModelTurn | None]:
    # The Runtime protocol remains tool-capable even while a compatibility
    # fixture has an empty registry; providers must reject that mismatch
    # before receiving a request.
    has_tools = True
    if not host.adapter.capabilities.supports_request(has_tools=has_tools):
        error = ModelProviderError(
            ModelErrorCode.CAPABILITY_MISMATCH,
            "model capabilities do not support this request",
        )
        yield host._event(context, "model.failed", safe_error_payload(error, 0))
        yield None
        return
    stream_id = f"stream_{uuid4().hex}"
    for attempt in range(1, host.retry_policy.max_attempts + 1):
        yield host._event(
            context,
            "model.requested",
            {"turn": context.model_turns, "attempt": attempt},
        )
        started = datetime.now(UTC)
        frame_index = 0
        try:
            turn: ModelTurn | None = None
            for item in host.adapter.stream(request):
                if isinstance(item, ModelTextDelta):
                    yield StreamFrame(
                        run_id=context.run_id,
                        stream_id=stream_id,
                        index=frame_index,
                        type=StreamFrameType.ASSISTANT_DELTA,
                        payload={"text": item.text},
                    )
                    frame_index += 1
                elif isinstance(item, ModelStreamCompleted):
                    turn = item.turn
            if turn is None:
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE,
                    "provider stream missing completion",
                )
        except ModelProviderError as provider_error:
            if not host.retry_policy.should_retry(provider_error, attempt):
                yield host._event(
                    context, "model.failed", safe_error_payload(provider_error, attempt)
                )
                yield None
                return
            delay = host.retry_policy.delay_seconds(provider_error, attempt)
            yield host._event(
                context,
                "model.retrying",
                {
                    "attempt": attempt,
                    "delay": delay,
                    "code": provider_error.code.value,
                },
            )
            host.sleep(delay)
            continue
        except Exception:
            mapped = ModelProviderError(ModelErrorCode.SERVICE, "provider request failed")
            yield host._event(context, "model.failed", safe_error_payload(mapped, attempt))
            yield None
            return
        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        usage = None
        if turn.usage is not None:
            usage = turn.usage.model_dump(mode="json")
        yield host._event(
            context,
            "model.completed",
            {
                "finish_reason": turn.finish_reason,
                "tool_call_count": len(turn.tool_calls),
                "attempt": attempt,
                "usage": usage,
                "request_id": turn.provider_request_id,
                "duration_ms": duration_ms,
                "stream_id": stream_id,
            },
        )
        yield turn
        return
    yield None


def drive(host: LoopFlowHost, context: RunContext) -> Iterator[RuntimeOutput]:
    halt = {
        RunState.AWAITING_APPROVAL,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.COMPLETED,
        RunState.VERIFICATION_FAILED,
        RunState.STALE,
    }
    while context.machine.state not in halt:
        if context.model_turns >= host.limits.max_model_turns:
            yield from host._fail(context, "max_model_turns")
            return
        context.context_bytes = message_bytes(context.messages)
        if context.context_bytes >= host.limits.max_context_bytes:
            context.messages = compact_run_messages(
                context.messages,
                max_bytes=host.limits.max_context_bytes,
            )
            context.context_bytes = message_bytes(context.messages)
        if context.context_bytes >= host.limits.max_context_bytes:
            yield from host._fail(context, "max_context_bytes")
            return
        context.model_turns += 1
        request = host._model_request(context)
        turn: ModelTurn | None = None
        for item in host._complete_with_retry(context, request):
            if isinstance(item, (EventEnvelope, StreamFrame)):
                yield item
            else:
                turn = item
        if context.machine.state == RunState.CANCELLED:
            return
        if turn is None:
            yield from host._fail(context, "model_error")
            return
        context.messages.append(
            ModelMessage(
                role="assistant",
                content=turn.assistant_text or "",
                tool_calls=turn.tool_calls,
                reasoning_content=turn.reasoning_content,
            )
        )
        if turn.assistant_text:
            _envelope, _rendered, flagged = host._prepare_content(
                context,
                turn.assistant_text,
                source_kind="model_output",
                origin="model.assistant",
            )
            yield from flagged
        if not turn.tool_calls:
            text = (turn.assistant_text or "").strip()
            if not text:
                if context.tool_calls > 0 and not context.empty_after_tools_nudge:
                    context.empty_after_tools_nudge = True
                    context.messages.append(
                        ModelMessage(role="user", content=_EMPTY_AFTER_TOOLS_NUDGE)
                    )
                    continue
                yield from host._fail(context, "empty_model_response")
                return
            has_approval = any(e.type == "approval.required" for e in context.journal.read_all())
            if (
                claims_unissued_changeset(text)
                and not context.claimed_changeset_nudge
                and not has_approval
            ):
                context.claimed_changeset_nudge = True
                context.messages.append(ModelMessage(role="assistant", content=text))
                context.messages.append(ModelMessage(role="user", content=_CLAIMED_CHANGESET_NUDGE))
                continue
            context.machine.transition(RunState.COMPLETED)
            yield host._event(
                context,
                "assistant.message",
                {
                    "content": text,
                    "stream_id": next(
                        (
                            event.payload.get("stream_id")
                            for event in reversed(context.journal.read_all())
                            if event.type == "model.completed"
                        ),
                        None,
                    ),
                },
            )
            yield host._stable_event(
                context,
                "run.completed",
                {"state": RunState.COMPLETED.value, "outcome": "responded"},
                RecoveryStage.TERMINAL,
            )
            return
        context.machine.transition(RunState.GENERATING)
        pending = list(turn.tool_calls)
        for index, call in enumerate(pending):
            if context.tool_calls >= host.limits.max_tool_calls:
                for skipped in pending[index:]:
                    context.messages.append(
                        ModelMessage(
                            role="tool",
                            content=_TOOL_LIMIT_SKIPPED,
                            tool_call_id=skipped.call_id,
                        )
                    )
                yield from host._finish_at_tool_limit(context)
                return
            context.tool_calls += 1
            encoded = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)
            _envelope, _rendered, flagged = host._prepare_content(
                context,
                encoded,
                source_kind="model_output",
                origin=f"model.tool_call:{call.name}",
            )
            yield from flagged
            yield from host._execute_tool(context, call)
            if context.machine.state in {
                RunState.AWAITING_APPROVAL,
                RunState.FAILED,
                RunState.CANCELLED,
            }:
                return
        if context.read_warning_pending:
            context.read_warning_pending = False
            context.messages.append(
                ModelMessage(
                    role="user",
                    content='{"core_notice":"Repeated reads produced no new evidence. Summarize '
                    "existing evidence or choose a different scope. Further unchanged reads will "
                    'stop this run. This is not an authorization."}',
                )
            )
        context.messages = compact_run_messages(
            context.messages,
            max_bytes=host.limits.max_context_bytes,
        )
        context.context_bytes = message_bytes(context.messages)
        context.machine.transition(RunState.DISCOVERING)


def finish_at_tool_limit(host: LoopFlowHost, context: RunContext) -> Iterator[RuntimeOutput]:
    if context.workspace_write_started or context.built_change_set is not None:
        yield from host._fail(context, "max_tool_calls")
        return
    if context.model_turns >= host.limits.max_model_turns:
        yield from host._fail(context, "max_tool_calls")
        return
    context.messages.append(ModelMessage(role="user", content=_TOOL_LIMIT_WRAP_UP))
    context.model_turns += 1
    request = ModelRequest(
        messages=tuple(context.messages),
        tools=(),
        max_output_tokens=4_096,
    )
    turn: ModelTurn | None = None
    for item in host._complete_with_retry(context, request):
        if isinstance(item, (EventEnvelope, StreamFrame)):
            yield item
        else:
            turn = item
    if turn is None or turn.tool_calls:
        yield from host._fail(context, "max_tool_calls")
        return
    text = (turn.assistant_text or "").strip()
    if not text:
        yield from host._fail(context, "max_tool_calls")
        return
    context.messages.append(
        ModelMessage(
            role="assistant",
            content=text,
            reasoning_content=turn.reasoning_content,
        )
    )
    context.machine.transition(RunState.DISCOVERING)
    context.machine.transition(RunState.COMPLETED)
    yield host._event(context, "assistant.message", {"content": text})
    yield host._stable_event(
        context,
        "run.completed",
        {"state": RunState.COMPLETED.value, "outcome": "responded"},
        RecoveryStage.TERMINAL,
    )


def compact(host: LoopFlowHost, context: RunContext) -> Iterator[RuntimeOutput]:
    request = ModelRequest(
        messages=tuple(context.messages),
        tools=(),
        max_output_tokens=4_096,
    )
    turn: ModelTurn | None = None
    for item in host._complete_with_retry(context, request):
        if isinstance(item, (EventEnvelope, StreamFrame)):
            yield item
        else:
            turn = item
    if turn is None:
        yield from host._fail(context, "model_error")
        return
    if turn.tool_calls:
        yield from host._fail(context, "invalid_compaction_response")
        return
    text = (turn.assistant_text or "").strip()
    if not text:
        yield from host._fail(context, "empty_model_response")
        return
    context.machine.transition(RunState.COMPLETED)
    _envelope, _rendered, flagged = host._prepare_content(
        context,
        text,
        source_kind="conversation_summary",
        origin="conversation.compacted",
    )
    yield from flagged
    yield host._event(context, "conversation.compacted", {"summary": text})
    yield host._event(
        context,
        "run.completed",
        {"state": RunState.COMPLETED.value, "outcome": "compacted"},
    )


class LoopFlow:
    """Stable façade for the model loop and tool dispatch."""

    execute_tool = staticmethod(execute_tool)
    complete_with_retry = staticmethod(complete_with_retry)
    drive = staticmethod(drive)
    finish_at_tool_limit = staticmethod(finish_at_tool_limit)
    compact = staticmethod(compact)
