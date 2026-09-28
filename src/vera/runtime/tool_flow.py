"""Tool execution, receipt, and tool-result projection flows."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Literal

from vera.content.trust import source_kind_for_path
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.tool_actions import ToolEffect
from vera.models.base import ModelMessage, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.persistence.operation_receipt import OperationReceipt, receipt_key
from vera.recovery.models import PendingGitOperation
from vera.recovery.resume import RunResumer
from vera.runtime.context import RunContext, tool_result_message
from vera.runtime.flow_protocols import ToolFlowHost
from vera.runtime.intake import tool_call_target
from vera.tools.definitions import ToolResult
from vera.tools.executor import PreparedToolAction, ToolExecutor
from vera.workspace.changeset import sha256_bytes


def replay_receipt(host: ToolFlowHost, receipt: OperationReceipt) -> Iterator[EventEnvelope]:
    path = host.state_dir / "runs" / receipt.run_id / "events.jsonl"
    if not path.is_file():
        return
    wanted = {ref.removeprefix("event:") for ref in receipt.effect_refs if ref.startswith("event:")}
    for event in EventJournal.load_events(path, receipt.run_id):
        if event.event_id in wanted:
            yield event


def file_effect_refs(host: ToolFlowHost, run_id: str) -> tuple[str, ...]:
    context = host.runs.get(run_id)
    if context is None or context.built_change_set is None:
        return ()
    refs: list[str] = []
    root = context.command.workspace_root
    for item in context.built_change_set.change_set.files:
        target = root / item.path
        digest = sha256_bytes(target.read_bytes()) if target.exists() else "0" * 64
        refs.append(f"file:{item.path}:{digest}")
    return tuple(refs)


def commit_receipt(
    host: ToolFlowHost,
    *,
    operation: Literal[
        "resume",
        "resolve_approval",
        "cancel",
        "rollback",
        "process",
        "git_commit",
        "git_branch",
    ],
    run_id: str,
    payload: dict[str, Any],
    events: Sequence[EventEnvelope],
    extra_refs: tuple[str, ...] = (),
) -> None:
    if not events:
        return
    operation_id, input_hash = receipt_key(operation, payload)
    host.receipts.save(
        OperationReceipt(
            operation_id=operation_id,
            operation=operation,
            run_id=run_id,
            input_hash=input_hash,
            terminal_result=events[-1].type,
            effect_refs=tuple(f"event:{event.event_id}" for event in events) + extra_refs,
            created_at=datetime.now(UTC),
        )
    )


def process_receipt_payload(prepared: PreparedToolAction) -> dict[str, str]:
    plan = prepared.process_plan
    if plan is None:
        raise ValueError("process receipt requires a process plan")
    return {
        "action_id": plan.action_id,
        "run_id": plan.run_id,
        "input_hash": plan.input_hash,
        "policy_hash": plan.policy_hash,
    }


def replayed_tool_result(events: Sequence[EventEnvelope]) -> ToolResult:
    for event in reversed(events):
        if event.type != "tool.completed":
            continue
        payload = event.payload
        return ToolResult(
            ok=bool(payload.get("ok", False)),
            truncated=bool(payload.get("truncated", False)),
            error_code=(str(payload["error_code"]) if payload.get("error_code") else None),
        )
    return ToolResult(ok=False, error_code="process_receipt_replayed")


def available_tool_scopes(
    prepared: PreparedToolAction,
) -> tuple[Literal["once", "run", "workspace"], ...]:
    action = prepared.action
    if action.tool_name in {"web_search", "web_read_result"}:
        return ("once",)
    if action.risk_facts.external_target is not None:
        return ("once", "run")
    if {
        ToolEffect.NETWORK_ACCESS,
        ToolEffect.EXTERNAL_SERVICE,
        ToolEffect.SECRET_ACCESS,
    }.intersection(action.effects):
        return ("once", "run")
    return ("once", "run", "workspace")


def execute_prepared(
    host: ToolFlowHost,
    context: RunContext,
    call: ModelToolCall,
    executor: ToolExecutor,
    prepared: PreparedToolAction,
    *,
    approved: bool = False,
) -> tuple[ToolResult, tuple[EventEnvelope, ...]]:
    if prepared.git_commit_plan is not None or prepared.git_branch_plan is not None:
        return execute_git(host, context, call, executor, prepared, approved=approved)
    if prepared.process_plan is None:
        result = executor.execute_allowed(prepared, approved=approved)
        events = tuple(emit_tool_result(host, context, call, result))
        return result, events

    payload = process_receipt_payload(prepared)
    operation_id, _input_hash = receipt_key("process", payload)
    existing = host.receipts.load(context.run_id, operation_id)
    if existing is not None:
        events = tuple(replay_receipt(host, existing))
        return replayed_tool_result(events), events

    context.process_in_flight = True
    started = host._stable_event(
        context,
        "process.started",
        {
            "action_id": prepared.action.action_id,
            "tool_name": prepared.action.tool_name,
            "input_hash": prepared.process_plan.input_hash,
        },
        RecoveryStage.STARTED,
    )
    result = executor.execute_allowed(prepared, approved=approved)
    context.process_in_flight = False
    status = result.content.get("status") if isinstance(result.content, dict) else None
    completed = host._stable_event(
        context,
        "process.completed",
        {
            "action_id": prepared.action.action_id,
            "tool_name": prepared.action.tool_name,
            "status": status or ("exited" if result.ok else "error"),
            "ok": result.ok,
            "error_code": result.error_code,
        },
        RecoveryStage.STARTED,
    )
    tool_events = tuple(emit_tool_result(host, context, call, result))
    events = (started, completed, *tool_events)
    commit_receipt(
        host,
        operation="process",
        run_id=context.run_id,
        payload=payload,
        events=events,
    )
    return result, events


def git_operation_payload(prepared: PreparedToolAction) -> dict[str, Any]:
    if prepared.git_commit_plan is not None:
        plan = prepared.git_commit_plan
        return {
            "operation": "git_commit",
            "plan_id": plan.plan_id,
            "expected_head_oid": plan.head_oid,
            "branch": plan.branch,
            "paths": list(plan.paths),
            "policy_hash": plan.policy_hash,
        }
    if prepared.git_branch_plan is not None:
        branch_plan = prepared.git_branch_plan
        return {
            "operation": "git_branch",
            "plan_id": branch_plan.action_id,
            "expected_head_oid": branch_plan.expected_head_oid,
            "expected_branch": branch_plan.expected_branch,
            "branch": branch_plan.branch_name,
            "policy_hash": branch_plan.policy_hash,
        }
    raise ValueError("git operation plan missing")


def execute_git(
    host: ToolFlowHost,
    context: RunContext,
    call: ModelToolCall,
    executor: ToolExecutor,
    prepared: PreparedToolAction,
    *,
    approved: bool,
) -> tuple[ToolResult, tuple[EventEnvelope, ...]]:
    if prepared.git_commit_plan is not None:
        context.pending_git_operation = PendingGitOperation.from_commit(prepared.git_commit_plan)
    elif prepared.git_branch_plan is not None:
        context.pending_git_operation = PendingGitOperation.from_branch(prepared.git_branch_plan)
    else:
        raise ValueError("git operation plan missing")
    operation_payload = git_operation_payload(prepared)
    started = host._stable_event(
        context,
        "git.operation.started",
        operation_payload,
        RecoveryStage.STARTED,
    )
    # A crash from the underlying transaction intentionally propagates. The
    # started event has already persisted the pending Git facts.
    result = executor.execute_allowed(prepared, approved=approved)
    error_code = result.error_code or ""
    if result.ok:
        recovered = bool(
            isinstance(result.content, dict) and result.content.get("recovered") is True
        )
        context.pending_git_operation = None
        terminal_type = "git.operation.recovered" if recovered else "git.operation.completed"
        terminal = host._stable_event(
            context,
            terminal_type,
            {**operation_payload, "ok": True},
            RecoveryStage.STARTED,
        )
    elif error_code == "manual_required":
        terminal = host._stable_event(
            context,
            "git.operation.manual_required",
            {**operation_payload, "ok": False, "error_code": error_code},
            RecoveryStage.STARTED,
        )
    else:
        context.pending_git_operation = None
        terminal = host._stable_event(
            context,
            "git.operation.failed",
            {**operation_payload, "ok": False, "error_code": error_code},
            RecoveryStage.STARTED,
        )
    tool_events = tuple(emit_tool_result(host, context, call, result))
    return result, (started, terminal, *tool_events)


def with_receipt(
    host: ToolFlowHost,
    operation: Literal["resume", "resolve_approval", "cancel", "rollback"],
    run_id: str,
    payload: dict[str, Any],
    events: Iterator[EventEnvelope],
    *,
    extra_refs: Callable[[], tuple[str, ...]] | None = None,
    hydrate: bool = False,
) -> Iterator[EventEnvelope]:
    operation_id, _input_hash = receipt_key(operation, payload)
    existing = host.receipts.load(run_id, operation_id)
    if existing is not None:
        if hydrate and run_id not in host.runs:
            with suppress(Exception):
                host.runs[run_id] = RunResumer(host.coordinator).load_context(run_id)
        yield from replay_receipt(host, existing)
        return
    collected: list[EventEnvelope] = []
    for event in events:
        collected.append(event)
        yield event
    refs = extra_refs() if extra_refs is not None else ()
    commit_receipt(
        host,
        operation=operation,
        run_id=run_id,
        payload=payload,
        events=collected,
        extra_refs=refs,
    )


def emit_tool_result(
    host: ToolFlowHost, context: RunContext, call: ModelToolCall, result: ToolResult
) -> Iterator[EventEnvelope]:
    target = tool_call_target(call)
    origin = call.name
    source_kind = "tool_output"
    if call.name in {"web_search", "web_read_result"}:
        source_kind = "external_web_page"
    if isinstance(call.arguments, dict) and call.arguments.get("path") is not None:
        relative = str(call.arguments.get("path"))
        origin = f"{call.name}:{relative}"
        if call.name in {"read", "read_file"}:
            source_kind = source_kind_for_path(relative)
    if result.content is None:
        text = ""
    else:
        text = json.dumps(result.content, ensure_ascii=False, sort_keys=True)
    envelope, rendered, events = host._prepare_content(
        context,
        text,
        source_kind=source_kind,
        origin=origin,
        truncated=bool(result.truncated),
    )
    yield from events
    payload = {
        "name": call.name,
        "call_id": call.call_id,
        "ok": result.ok,
        "truncated": result.truncated,
        "error_code": result.error_code,
        "source_kind": envelope.source_kind,
        "trust_level": envelope.trust_level.value,
        "content_hash": envelope.content_hash,
    }
    if context.active_tool_span_id is not None:
        payload["span_id"] = context.active_tool_span_id
    if target:
        payload["target"] = target
    if call.name in {"web_search", "web_read_result"} and isinstance(result.content, dict):
        payload["provider_id"] = result.content.get("provider_id")
        payload["query_id"] = result.content.get("query_id")
        if call.name == "web_search":
            results = result.content.get("results")
            if isinstance(results, list):
                payload["source_count"] = len(results)
                payload["sources"] = [
                    {
                        "source_id": item.get("source_id"),
                        "canonical_url": item.get("canonical_url"),
                    }
                    for item in results
                    if isinstance(item, dict)
                ]
        else:
            payload["source_id"] = result.content.get("source_id")
            payload["canonical_url"] = result.content.get("canonical_url")
    mutation_payload = result.content if call.name in {"write", "edit"} else None
    if isinstance(mutation_payload, dict) and mutation_payload.get("action_id"):
        yield host._event(
            context,
            "file_mutation.planned",
            {
                "action_id": mutation_payload.get("action_id"),
                "operation": mutation_payload.get("operation"),
                "path": mutation_payload.get("path"),
                "before_hash": mutation_payload.get("before_hash"),
                "after_hash": mutation_payload.get("after_hash"),
                "unified_diff": mutation_payload.get("unified_diff"),
            },
        )
    yield host._event(context, "tool.completed", payload)
    if isinstance(mutation_payload, dict) and mutation_payload.get("action_id") and result.ok:
        context.applied_file_mutations.append(
            {
                "action_id": str(mutation_payload.get("action_id")),
                "path": str(mutation_payload.get("path")),
                "unified_diff": str(mutation_payload.get("unified_diff", "")),
            }
        )
        yield host._event(
            context,
            "file_mutation.applied",
            {
                "action_id": mutation_payload.get("action_id"),
                "path": mutation_payload.get("path"),
                "status": mutation_payload.get("status", "applied"),
                "cumulative_diff": list(context.applied_file_mutations),
            },
        )
    tool_text = tool_result_message(call, result, rendered)
    context.messages.append(ModelMessage(role="tool", content=tool_text, tool_call_id=call.call_id))
    context.context_bytes = sum(
        len(message.content.encode("utf-8")) for message in context.messages
    )


class ToolExecutionFlow:
    """Stable façade for Runtime's extracted tool execution operations."""

    execute_prepared = staticmethod(execute_prepared)
    execute_git = staticmethod(execute_git)
    available_tool_scopes = staticmethod(available_tool_scopes)
    process_receipt_payload = staticmethod(process_receipt_payload)
    replayed_tool_result = staticmethod(replayed_tool_result)
    git_operation_payload = staticmethod(git_operation_payload)
    emit_tool_result = staticmethod(emit_tool_result)
    with_receipt = staticmethod(with_receipt)
