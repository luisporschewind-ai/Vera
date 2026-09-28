"""Session action dispatch and active Run lifecycle flow."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal

from vera.contracts.commands import CancelRun, ResolveApproval, ResumeRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    ResolveSessionApproval,
    SessionAction,
    SubmitPrompt,
)
from vera.session.flow_constants import _TERMINAL_TYPES, _UNSAVED_ADVICE

if TYPE_CHECKING:
    from vera.session.controller import SessionController


def dispatch(host: SessionController, action: SessionAction) -> Iterator[RuntimeOutput]:
    if host._closed:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": "session_closed", "message": "会话已关闭。"},
        )
        return
    match action:
        case SubmitPrompt(text=text):
            host.history.record(text)
            yield from host._submit(text)
        case ExecuteSlashCommand(raw=raw):
            yield from host._slash(raw)
        case ResolveSessionApproval(approval_id=approval_id, decision=decision):
            yield from host._resolve_approval(approval_id, decision)
        case CancelActiveRun(run_id=run_id):
            yield from host._cancel(run_id)
        case CloseSession():
            yield from host._close()
        case QueuePrompt(text=text):
            yield from host._queue_prompt(text)
        case ClearQueuedPrompt():
            yield from host._clear_queued_prompt()
        case ConfirmExternalEditor(accept=accept):
            yield from host._confirm_editor(accept)
        case OpenExternalEditor(text=text):
            yield from host._open_editor(text)


def submit(host: SessionController, text: str) -> Iterator[RuntimeOutput]:
    if host._active_run_id is not None:
        yield host._session_event(
            "session.action_rejected",
            {
                "reason_code": "run_active",
                "message": "当前有运行中的任务，请先等待、取消或完成审批。",
            },
        )
        return
    if not host.conversation.can_accept(text):
        yield host._session_event(
            "session.message",
            {"text": "当前上下文已满。请先执行 /compact 或 /new。"},
        )
        return
    command = StartRun(
        goal=text,
        workspace_root=host.workspace,
        model_profile=host.model_profile,
        conversation=host.conversation.snapshot(),
    )
    host._goal_for_active = text
    host._events_for_active = []
    yield host._session_event("session.user_prompt", {"text": text})
    yield from host._drive(command)


def queue_prompt(host: SessionController, text: str) -> Iterator[RuntimeOutput]:
    if host._pending_approval is not None:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": "approval_pending", "message": "等待审批时不能排队下一条输入。"},
        )
        return
    if host._active_run_id is None:
        host.history.record(text)
        yield from host._submit(text)
        return
    if host.queued_prompt is not None:
        yield host._session_event(
            "session.action_rejected",
            {
                "reason_code": "queue_occupied",
                "message": "已有一条排队输入，请先撤销再替换。",
                "queued": True,
            },
        )
        return
    host.queued_prompt = text
    host.history.record(text)
    yield host._session_event("session.prompt_queued", {"queued": True})


def clear_queued_prompt(host: SessionController) -> Iterator[RuntimeOutput]:
    if host.queued_prompt is None:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": "queue_empty", "message": "当前没有排队输入。"},
        )
        return
    host.queued_prompt = None
    yield host._session_event("session.prompt_queue_cleared", {"queued": False})


def resolve_approval(
    host: SessionController, approval_id: str, decision: Literal["approve", "reject", "cancel"]
) -> Iterator[RuntimeOutput]:
    pending = host._pending_approval
    if pending is None or host._active_run_id is None:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": "no_pending_approval", "message": "当前没有待处理审批。"},
        )
        return
    pending_id = str(pending.payload.get("approval_id", ""))
    if pending_id != approval_id:
        yield host._session_event(
            "session.action_rejected",
            {
                "reason_code": "approval_mismatch",
                "message": "审批 ID 不匹配。",
                "expected": pending_id,
                "received": approval_id,
            },
        )
        return
    run_id = host._active_run_id
    host._pending_approval = None
    if decision == "cancel":
        yield from host._drive(CancelRun(run_id=run_id))
        return
    yield from host._drive(
        ResolveApproval(
            run_id=run_id,
            approval_id=approval_id,
            target_hash=str(pending.payload["target_hash"]),
            decision=decision,
        )
    )


def cancel(host: SessionController, run_id: str) -> Iterator[RuntimeOutput]:
    if host._active_run_id is None:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": "no_active_run", "message": "当前没有可取消的任务。"},
        )
        return
    if run_id != host._active_run_id:
        yield host._session_event(
            "session.action_rejected",
            {
                "reason_code": "run_mismatch",
                "message": "取消目标与当前任务不一致。",
                "active_run_id": host._active_run_id,
                "requested_run_id": run_id,
            },
        )
        return
    host._pending_approval = None
    yield from host._drive(CancelRun(run_id=run_id))


def close(host: SessionController) -> Iterator[RuntimeOutput]:
    if host.dependencies.runtime.access_session is not None:
        host.dependencies.runtime.access_session.close()
    host.queued_prompt = None
    if host._pending_approval is not None and host._active_run_id is not None:
        approval_id = str(host._pending_approval.payload.get("approval_id", ""))
        yield from host._resolve_approval(approval_id, "cancel")
    if host._active_run_id is not None:
        yield from host._cancel(host._active_run_id)
    if host._persistence_state == "unsaved":
        yield host._session_event(
            "session.close_warning",
            {
                "state": "unsaved",
                "error_code": host._last_error_code or "write_failed",
                "advice": _UNSAVED_ADVICE,
            },
        )
    else:
        try:
            record = host.session_store.close(host.conversation.stats().session_id, "user_close")
            host._last_saved_sequence = record.sequence
        except Exception as exc:
            yield host._mark_unsaved(host._persistence_code(exc))
            yield host._session_event(
                "session.close_warning",
                {
                    "state": "unsaved",
                    "error_code": host._last_error_code or "write_failed",
                    "advice": _UNSAVED_ADVICE,
                },
            )
    host._closed = True
    host.exit_requested = True
    host.history.clear()
    host.queued_prompt = None
    yield host._session_event("session.closed", {"reason": "user_close"})


def drive(
    host: SessionController,
    command: StartRun | ResolveApproval | CancelRun | ResumeRun,
    *,
    record_conversation: bool = True,
) -> Iterator[RuntimeOutput]:
    produced_terminal = False
    epoch = host._drive_epoch
    for output in host.dependencies.runtime.stream(command):
        if host._drive_epoch != epoch:
            return
        if isinstance(output, EventEnvelope):
            host._events_for_active.append(output)
            if output.type == "run.started" or (
                host._active_run_id is None and output.type not in _TERMINAL_TYPES
            ):
                host._active_run_id = output.run_id
            if output.type == "project.instructions.loaded":
                digest = output.payload.get("guidance_hash")
                host._run_guidance_hash = digest if isinstance(digest, str) else None
            if output.type == "approval.required":
                host._active_run_id = output.run_id
                host._pending_approval = output
                yield output
                return
            if output.type in _TERMINAL_TYPES:
                produced_terminal = True
        yield output
    if host._drive_epoch != epoch:
        return
    if produced_terminal or host._pending_approval is None:
        yield from host._finish_active_run(record_conversation=record_conversation)
        queued = host.queued_prompt
        if queued and host._active_run_id is None and not host._closed:
            host.queued_prompt = None
            yield host._session_event("session.prompt_queue_flushed", {"queued": True})
            yield from host._submit(queued)


def finish_active_run(
    host: SessionController, *, record_conversation: bool = True
) -> Iterator[RuntimeOutput]:
    host._drive_epoch += 1
    goal = host._goal_for_active
    events = tuple(host._events_for_active)
    host._active_run_id = None
    host._pending_approval = None
    host._goal_for_active = None
    host._events_for_active = []
    if record_conversation and goal is not None and events:
        yield from host._persist_turn(goal, events)


class SessionRunFlow:
    """Stable façade for session actions and active Run lifecycle."""

    dispatch = staticmethod(dispatch)
    submit = staticmethod(submit)
    queue_prompt = staticmethod(queue_prompt)
    clear_queued_prompt = staticmethod(clear_queued_prompt)
    resolve_approval = staticmethod(resolve_approval)
    cancel = staticmethod(cancel)
    close = staticmethod(close)
    drive = staticmethod(drive)
    finish_active_run = staticmethod(finish_active_run)
