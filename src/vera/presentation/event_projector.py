"""Runtime event-to-timeline projection flow."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import (
    event_summary,
    event_title,
    format_recovery_inspection,
    format_tool_body,
    format_tool_title,
    is_silent,
)
from vera.presentation.mutations import AppendBlock, TimelineMutation, UpdateBlock
from vera.presentation.prompt_block import project_user_prompt
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.session_event_handlers import (
    instruction_status,
    persistence_warning,
    session_config,
    session_doctor,
    session_loaded,
    session_message,
    session_status,
)
from vera.presentation.timeline import BlockKind, BlockStatus

if TYPE_CHECKING:
    from vera.presentation.projector import TimelineProjector

_SIDE_EFFECT_EVENTS = frozenset(
    {
        "changeset.applied",
        "verification.started",
        "verification.completed",
        "rollback.completed",
        "recovery.resumed",
    }
)


def apply_event(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    handlers = {
        "run.started": host._status_event,
        "assistant.message": host._assistant_message,
        "tool.started": host._tool_started,
        "tool.completed": host._tool_completed,
        "changeset.proposed": host._changeset_proposed,
        "approval.required": host._approval_required,
        "approval.resolved": host._status_event,
        "approval.expired": host._approval_expired,
        "approval.invalidated": host._approval_expired,
        "checkpoint.created": host._status_event,
        "changeset.applied": host._changeset_applied,
        "verification.started": host._verification_started,
        "verification.completed": host._verification_completed,
        "run.completed": host._terminal_status,
        "run.failed": host._run_failed,
        "run.cancelled": host._run_cancelled,
        "git.operation.started": host._git_operation_event,
        "git.operation.completed": host._git_operation_event,
        "git.operation.recovered": host._git_operation_event,
        "git.operation.manual_required": host._git_operation_event,
        "git.operation.failed": host._git_operation_event,
        "recovery.detected": host._recovery_event,
        "recovery.manual_required": host._recovery_event,
        "conversation.compacted": host._status_event,
        "session.status": host._session_status,
        "session.message": host._session_message,
        "session.user_prompt": host._user_prompt,
        "session.help": host._session_message,
        "session.doctor": host._session_doctor,
        "session.theme": host._session_message,
        "session.shortcuts": host._session_message,
        "session.config": host._session_config,
        "session.usage": host._session_message,
        "session.trace": host._session_message,
        "skill.listed": host._session_message,
        "skill.shown": host._session_message,
        "skill.selection.changed": host._session_message,
        "skill.snapshot.bound": host._session_message,
        "session.permissions": host._session_message,
        "session.review": host._session_message,
        "session.diff": host._session_diff,
        "session.action_rejected": host._error_event,
        "session.closed": host._status_event,
        "session.persistence_changed": host._persistence_warning,
        "session.close_warning": host._persistence_warning,
        "session.loaded": host._session_loaded,
        "session.listed": host._session_message,
        "session.load_failed": host._persistence_warning,
        "project.instructions.loaded": host._instruction_status,
        "project.instructions.skipped": host._instruction_status,
        "project.instructions.status": host._instruction_status,
    }
    if event.type in _SIDE_EFFECT_EVENTS:
        host._side_effect_runs.add(event.run_id)
    if event.type == "model.failed":
        host._model_failures[event.run_id] = dict(event.payload)
    if is_silent(event.type):
        return ()
    handler = handlers.get(event.type, host._unknown_event)
    return host._with_occurred_at(handler(event), event.timestamp)


def assistant_message(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    content = str(event.payload.get("content", event.payload.get("text", "")))
    stream_id = event.payload.get("stream_id")
    if isinstance(stream_id, str) and stream_id:
        block_id = f"{event.run_id}:{stream_id}:assistant"
        existing = host._blocks.get(block_id)
        if existing is not None:
            updated = existing.model_copy(
                update={
                    "body": sanitize_terminal_text(content),
                    "status": BlockStatus.SUCCEEDED,
                    "incomplete": False,
                }
            )
            host._blocks[block_id] = updated
            return (UpdateBlock(block=updated),)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:assistant",
        run_id=event.run_id,
        kind=BlockKind.ASSISTANT,
        title="Vera",
        body=content,
        status=BlockStatus.SUCCEEDED,
    )


def tool_started(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    name = str(event.payload.get("name", "tool"))
    block_id = f"{event.run_id}:{event.sequence}:tool"
    call_id = str(event.payload.get("call_id", event.sequence))
    target = str(event.payload.get("target") or "")
    host._tool_blocks[(event.run_id, call_id)] = block_id
    host._tool_blocks[(event.run_id, name)] = block_id
    host._tool_started_at[(event.run_id, call_id)] = event.timestamp
    return host._append(
        block_id=block_id,
        run_id=event.run_id,
        kind=BlockKind.TOOL,
        title=format_tool_title(name, target=target, status="running"),
        body=format_tool_body(target=target, status="running"),
        status=BlockStatus.RUNNING,
    )


def tool_completed(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    name = str(event.payload.get("name", "tool"))
    ok = bool(event.payload.get("ok", True))
    status = BlockStatus.SUCCEEDED if ok else BlockStatus.FAILED
    call_id = str(event.payload.get("call_id", ""))
    target = str(event.payload.get("target") or "")
    started_at = host._tool_started_at.pop((event.run_id, call_id), None)
    duration_ms: int | None = None
    raw_duration = event.payload.get("duration_ms")
    if isinstance(raw_duration, int):
        duration_ms = raw_duration
    elif started_at is not None:
        duration_ms = max(0, int((event.timestamp - started_at).total_seconds() * 1000))
    status_key = "completed" if ok else "failed"
    error = str(event.payload.get("error") or "")
    error_code = str(event.payload.get("error_code") or "")
    truncated = bool(event.payload.get("truncated", False))
    body = format_tool_body(
        target=target,
        status=status_key,
        duration_ms=duration_ms,
        error=error,
        error_code=error_code,
        truncated=truncated,
    )
    if name == "web_search" and ok:
        count = event.payload.get("source_count")
        sources = event.payload.get("sources")
        lines = [f"来源数量：{count}"] if isinstance(count, int) else []
        if isinstance(sources, list):
            lines.extend(
                f"{item.get('source_id')}：{item.get('canonical_url')}"
                for item in sources
                if isinstance(item, dict)
            )
        body = "\n".join(part for part in (body, *lines) if part)
    elif name == "web_read_result" and ok:
        source_url = event.payload.get("canonical_url")
        if isinstance(source_url, str):
            body = "\n".join(part for part in (body, f"来源：{source_url}") if part)
    title = format_tool_title(name, target=target, status=status_key, duration_ms=duration_ms)
    block_id = host._tool_blocks.get((event.run_id, call_id)) or host._tool_blocks.get(
        (event.run_id, name)
    )
    if block_id and block_id in host._blocks:
        existing = host._blocks[block_id]
        if not target:
            target = existing.body.partition("目标：")[2].split("\n", 1)[0]
            if target:
                title = format_tool_title(
                    name, target=target, status=status_key, duration_ms=duration_ms
                )
                body = format_tool_body(
                    target=target,
                    status=status_key,
                    duration_ms=duration_ms,
                    error=error,
                    error_code=error_code,
                    truncated=truncated,
                )
        updated = host.disclosure.on_status_change(existing, status).model_copy(
            update={
                "title": sanitize_terminal_text(title),
                "body": sanitize_terminal_text(body),
            }
        )
        host._blocks[block_id] = updated
        return (UpdateBlock(block=updated),)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:tool",
        run_id=event.run_id,
        kind=BlockKind.TOOL,
        title=title,
        body=body,
        status=status,
    )


def user_prompt(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    text = str(event.payload.get("text", ""))
    if not text.strip():
        return ()
    block = project_user_prompt(event.run_id, text, event.sequence, occurred_at=event.timestamp)
    host._blocks[block.block_id] = block
    host._evict_if_needed()
    return (AppendBlock(block=block),)


def changeset_proposed(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    files = event.payload.get("files", [])
    parts: list[str] = []
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", ""))
            diff = str(item.get("unified_diff", ""))
            parts.append(f"{path}\n{diff}".rstrip())
    body = "\n\n".join(parts)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:diff",
        run_id=event.run_id,
        kind=BlockKind.DIFF,
        title=f"Diff · {len(parts)} files",
        body=body,
        status=BlockStatus.PENDING,
    )


def session_diff(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    files = event.payload.get("files", [])
    text = str(event.payload.get("text") or "").strip()
    count = len(files) if isinstance(files, list) else 0
    body = text if text else "没有 Diff。"
    applied = event.payload.get("applied")
    if count and applied is False:
        title = f"Diff · {count} files · 未写入"
    elif count:
        title = f"Diff · {count} files"
    else:
        title = "Diff"
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:diff",
        run_id=event.run_id,
        kind=BlockKind.DIFF,
        title=title,
        body=sanitize_terminal_text(body),
        status=BlockStatus.FAILED if applied is False else BlockStatus.SUCCEEDED,
    )


def approval_required(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    risk = str(event.payload.get("risk", "unknown"))
    kind = str(event.payload.get("kind", "changeset"))
    approval_id = str(event.payload.get("approval_id", "unknown"))
    target = str(event.payload.get("target") or event.payload.get("target_id") or "")
    workspace = str(event.payload.get("workspace") or event.payload.get("workspace_root") or "")
    effect = str(
        event.payload.get("effect") or event.payload.get("description") or "批准后才会执行该动作"
    )
    argv = event.payload.get("argv", [])
    command = shlex.join(str(part) for part in argv) if isinstance(argv, list) and argv else ""
    profile = event.payload.get("artifact_profile") if kind == "command" else None
    root = event.payload.get("artifact_root") if kind == "command" else None
    cwd = event.payload.get("cwd")
    service = event.payload.get("service")
    query = event.payload.get("query")
    source_url = event.payload.get("source_url")
    max_results = event.payload.get("max_results")
    available_scopes = event.payload.get("available_scopes", [])
    scopes = (
        ", ".join(str(scope) for scope in available_scopes)
        if isinstance(available_scopes, list) and available_scopes
        else ""
    )
    body = "\n".join(
        part
        for part in (
            f"动作 {kind}",
            f"命令 {command}" if command else "",
            f"Profile {profile}" if profile else "",
            f"产物根 {root}" if root else "",
            f"工作目录 {cwd}" if cwd else "",
            f"服务 {service}" if service else "",
            f"实际查询 {query}" if query else "",
            f"来源 {source_url}" if source_url else "",
            f"结果上限 {max_results}" if max_results else "",
            f"目标 {target}" if target and not command else "",
            f"风险 {risk}",
            f"授权范围 {scopes}" if scopes else "",
            f"工作区 {workspace}" if workspace else "",
            f"效果 {effect}",
        )
        if part
    )
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:approval",
        run_id=event.run_id,
        kind=BlockKind.APPROVAL,
        title=f"Approval required · {kind} · {risk}",
        body=sanitize_terminal_text(body),
        status=BlockStatus.PENDING,
        focus=True,
        ref_id=approval_id,
    )


def approval_expired(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    from vera.presentation.errors import format_failure_body

    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:error",
        run_id=event.run_id,
        kind=BlockKind.ERROR,
        title="审批已过期",
        body=format_failure_body(event),
        status=BlockStatus.FAILED,
    )


def verification_started(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    argv = event.payload.get("argv", [])
    title = "Verification · running"
    body = " ".join(str(part) for part in argv) if isinstance(argv, list) else str(argv)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:verification",
        run_id=event.run_id,
        kind=BlockKind.VERIFICATION,
        title=title,
        body=body,
        status=BlockStatus.RUNNING,
    )


def verification_completed(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    result = str(event.payload.get("status", "unknown"))
    failed = result not in {"passed", "ok", "succeeded"}
    status = BlockStatus.FAILED if failed else BlockStatus.SUCCEEDED
    block_id = f"{event.run_id}:{event.sequence}:verification"
    # Prefer updating the most recent verification block for this run.
    existing_id = next(
        (
            key
            for key, block in reversed(list(host._blocks.items()))
            if block.run_id == event.run_id and block.kind is BlockKind.VERIFICATION
        ),
        None,
    )
    body = sanitize_terminal_text(
        str(event.payload.get("stderr") or event.payload.get("stdout") or result)
    )
    if existing_id is not None:
        existing = host._blocks[existing_id]
        updated = host.disclosure.on_status_change(existing, status).model_copy(
            update={
                "title": sanitize_terminal_text(
                    f"Verification · {'failed' if failed else 'passed'}"
                ),
                "body": body or existing.body,
            }
        )
        host._blocks[existing_id] = updated
        return (UpdateBlock(block=updated),)
    return host._append(
        block_id=block_id,
        run_id=event.run_id,
        kind=BlockKind.VERIFICATION,
        title=f"Verification · {'failed' if failed else 'passed'}",
        body=body,
        status=status,
    )


def run_failed(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    from vera.presentation.errors import format_failure_body

    return host._unapplied_diffs(event.run_id) + host._append(
        block_id=f"{event.run_id}:{event.sequence}:error",
        run_id=event.run_id,
        kind=BlockKind.ERROR,
        title="任务失败",
        body=format_failure_body(
            event,
            side_effects=host._side_effects_for(event.run_id),
            diagnostics=host._model_failures.get(event.run_id),
        ),
        status=BlockStatus.FAILED,
    )


def run_cancelled(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    from vera.presentation.errors import format_failure_body

    return host._unapplied_diffs(event.run_id) + host._append(
        block_id=f"{event.run_id}:{event.sequence}:error",
        run_id=event.run_id,
        kind=BlockKind.ERROR,
        title="已取消",
        body=format_failure_body(
            event,
            side_effects=host._side_effects_for(event.run_id),
        ),
        status=BlockStatus.CANCELLED,
    )


def recovery_event(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    if event.type == "recovery.manual_required":
        from vera.presentation.errors import format_failure_body

        return host._append(
            block_id=f"{event.run_id}:{event.sequence}:error",
            run_id=event.run_id,
            kind=BlockKind.ERROR,
            title=event_title(event.type),
            body=format_failure_body(event),
            status=BlockStatus.FAILED,
        )
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:recovery",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=event_title(event.type),
        body=format_recovery_inspection(event.run_id, event.payload),
        status=BlockStatus.SUCCEEDED,
    )


def git_operation_event(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    failed = event.type in {"git.operation.failed", "git.operation.manual_required"}
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:git",
        run_id=event.run_id,
        kind=BlockKind.ERROR if failed else BlockKind.STATUS,
        title=event_title(event.type),
        body=sanitize_terminal_text(event_summary(event.payload)),
        status=BlockStatus.FAILED if failed else BlockStatus.SUCCEEDED,
    )


def error_event(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    from vera.presentation.errors import format_failure_body

    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:error",
        run_id=event.run_id,
        kind=BlockKind.ERROR,
        title="Error",
        body=format_failure_body(event),
        status=BlockStatus.FAILED,
    )


def terminal_status(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    return host._status_event(event)


def status_event(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:status",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=event_title(event.type),
        body=event_summary(event.payload),
        status=BlockStatus.SUCCEEDED,
    )


def unknown_event(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    return host._status_event(event)


class EventProjector:
    """Stable façade for Runtime event projection."""

    apply = staticmethod(apply_event)
    assistant_message = staticmethod(assistant_message)
    tool_started = staticmethod(tool_started)
    tool_completed = staticmethod(tool_completed)
    user_prompt = staticmethod(user_prompt)
    changeset_proposed = staticmethod(changeset_proposed)
    session_diff = staticmethod(session_diff)
    approval_required = staticmethod(approval_required)
    approval_expired = staticmethod(approval_expired)
    verification_started = staticmethod(verification_started)
    verification_completed = staticmethod(verification_completed)
    run_failed = staticmethod(run_failed)
    run_cancelled = staticmethod(run_cancelled)
    recovery_event = staticmethod(recovery_event)
    git_operation_event = staticmethod(git_operation_event)
    error_event = staticmethod(error_event)
    terminal_status = staticmethod(terminal_status)
    session_status = staticmethod(session_status)
    session_doctor = staticmethod(session_doctor)
    session_config = staticmethod(session_config)
    session_message = staticmethod(session_message)
    persistence_warning = staticmethod(persistence_warning)
    instruction_status = staticmethod(instruction_status)
    session_loaded = staticmethod(session_loaded)
    status_event = staticmethod(status_event)
    unknown_event = staticmethod(unknown_event)
