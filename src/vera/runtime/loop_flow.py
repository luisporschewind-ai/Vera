"""Runtime model loop and tool-dispatch flow."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.streaming import RuntimeOutput, StreamFrame, StreamFrameType
from vera.contracts.trace import TraceSpanStatus
from vera.models.base import ModelMessage, ModelRequest, ModelToolCall, ModelTurn
from vera.models.errors import ModelErrorCode, ModelProviderError, safe_error_payload
from vera.models.streaming import ModelStreamCompleted, ModelTextDelta
from vera.recovery.models import PersistedToolAction
from vera.runtime.approval import ApprovalKind
from vera.runtime.context import RunContext, compact_run_messages
from vera.runtime.flow_protocols import LoopFlowHost
from vera.runtime.intake import (
    _CLAIMED_CHANGESET_NUDGE,
    _EMPTY_AFTER_TOOLS_NUDGE,
    _TOOL_LIMIT_SKIPPED,
    _TOOL_LIMIT_WRAP_UP,
    claims_unissued_changeset,
    tool_call_target,
)
from vera.runtime.state import RunState
from vera.tools.executor import ToolPreparationError
from vera.trace.context_inventory import ContextInventory


def _execute_tool_inner(
    host: LoopFlowHost, context: RunContext, call: ModelToolCall
) -> Iterator[EventEnvelope]:
    signature = f"{call.name}:{call.arguments}"
    if context.last_tool_signature == signature:
        context.repeated_tool_streak += 1
    else:
        context.last_tool_signature = signature
        context.repeated_tool_streak = 1
    if context.repeated_tool_streak >= 3:
        yield from host._fail(context, "repeated_tool_call")
        return
    started: dict[str, Any] = {
        "name": call.name,
        "call_id": call.call_id,
        "span_id": context.active_tool_span_id,
    }
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
            f"execute tool {prepared.action.tool_name}",
            "high",
            workspace_identity=prepared.action.workspace_identity,
            policy_hash=prepared.policy_decision.policy_hash,
            fact_hash=prepared.target_facts_hash,
            available_scopes=host._available_tool_scopes(prepared),
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


def execute_tool(
    host: LoopFlowHost, context: RunContext, call: ModelToolCall
) -> Iterator[EventEnvelope]:
    input_body = json.dumps(
        call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    attributes: dict[str, Any] = {
        "tool_name": call.name[:128],
        "tool_call_id": call.call_id[:128],
        "input_byte_count": len(input_body),
        "input_content_hash": hashlib.sha256(input_body).hexdigest(),
    }
    span = context.trace_recorder.start_span("tool", call.name[:128], attributes=attributes)
    before = len(context.messages)
    status: TraceSpanStatus = "ok"
    error_code: str | None = None
    truncated = False
    completed = False
    context.active_tool_span_id = span.span_id
    try:
        for event in _execute_tool_inner(host, context, call):
            if event.type == "tool.completed":
                if not event.payload.get("ok", False):
                    status = "rejected" if call.parse_error else "error"
                    raw = event.payload.get("reason_code") or event.payload.get("error_code")
                    error_code = str(raw)[:128] if raw else None
                truncated = bool(event.payload.get("truncated", False))
            elif event.type == "approval.required":
                status = "unknown"
            elif event.type == "run.failed":
                status = "rejected"
                error_code = "repeated_tool_call"
            yield event
        completed = True
    except GeneratorExit:
        status = "interrupted"
        raise
    except Exception:
        status = "error"
        error_code = "tool_execution_error"
        raise
    finally:
        context.active_tool_span_id = None
        if not completed and status == "ok":
            status = "interrupted"
        messages = [
            message
            for message in context.messages[before:]
            if message.role == "tool" and message.tool_call_id == call.call_id
        ]
        output = messages[-1].content.encode("utf-8") if messages else b""
        finished = {
            **attributes,
            "output_byte_count": len(output),
            "output_content_hash": hashlib.sha256(output).hexdigest(),
            "truncated": truncated,
        }
        if error_code is not None:
            finished["error_code"] = error_code
        context.trace_recorder.finish_span(span, status, attributes=finished)


def complete_with_retry(
    host: LoopFlowHost, context: RunContext, request: ModelRequest
) -> Iterator[EventEnvelope | StreamFrame | ModelTurn | None]:
    # The Runtime protocol remains tool-capable with an empty compatibility registry.
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
    previous_span_id: str | None = None
    for attempt in range(1, host.retry_policy.max_attempts + 1):
        context.request_index += 1
        snapshot = ContextInventory.build(
            request,
            context,
            request_index=context.request_index,
            context_budget_bytes=host.limits.max_context_bytes,
        )
        identity = getattr(host.adapter, "identity", None)
        span_attributes: dict[str, Any] = {"attempt": attempt}
        if identity is not None:
            span_attributes.update(identity.model_dump(mode="json", exclude_none=True))
        if previous_span_id is not None:
            span_attributes["retry_of_span_id"] = previous_span_id
        span = context.trace_recorder.start_span(
            "llm", "provider attempt", attributes=span_attributes
        )
        context.trace_recorder.record_context(span, snapshot)
        yield host._event(
            context,
            "model.requested",
            {
                "turn": context.model_turns,
                "attempt": attempt,
                "span_id": span.span_id,
                "snapshot_id": snapshot.snapshot_id,
            },
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
            context.trace_recorder.finish_span(
                span,
                "error",
                attributes={"error_code": provider_error.code.value},
            )
            previous_span_id = span.span_id
            if not host.retry_policy.should_retry(provider_error, attempt):
                yield host._event(
                    context,
                    "model.failed",
                    {
                        **safe_error_payload(provider_error, attempt),
                        "span_id": span.span_id,
                    },
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
                    "span_id": span.span_id,
                },
            )
            host.sleep(delay)
            continue
        except Exception:
            mapped = ModelProviderError(ModelErrorCode.SERVICE, "provider request failed")
            context.trace_recorder.finish_span(
                span, "error", attributes={"error_code": mapped.code.value}
            )
            yield host._event(
                context,
                "model.failed",
                {**safe_error_payload(mapped, attempt), "span_id": span.span_id},
            )
            yield None
            return
        except GeneratorExit:
            context.trace_recorder.finish_span(span, "interrupted")
            raise
        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        usage = None
        if turn.usage is not None:
            usage = turn.usage.model_dump(mode="json")
        span_usage = (
            {key: value for key, value in usage.items() if value is not None}
            if usage is not None
            else {}
        )
        completed_attributes: dict[str, Any] = {
            "finish_reason": turn.finish_reason[:200],
            "tool_call_count": len(turn.tool_calls),
            **span_usage,
        }
        if turn.provider_request_id:
            completed_attributes["request_id"] = turn.provider_request_id[:200]
        context.trace_recorder.finish_span(span, "ok", attributes=completed_attributes)
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
                "span_id": span.span_id,
                "snapshot_id": snapshot.snapshot_id,
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
        if context.context_bytes >= host.limits.max_context_bytes:
            context.messages = compact_run_messages(
                context.messages,
                max_bytes=host.limits.max_context_bytes,
            )
            context.context_bytes = sum(
                len(message.content.encode("utf-8")) for message in context.messages
            )
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
            if claims_unissued_changeset(text) and not context.claimed_changeset_nudge:
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
        context.messages = compact_run_messages(
            context.messages,
            max_bytes=host.limits.max_context_bytes,
        )
        context.context_bytes = sum(
            len(message.content.encode("utf-8")) for message in context.messages
        )
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
