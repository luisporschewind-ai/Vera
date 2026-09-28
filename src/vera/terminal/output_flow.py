"""Runtime-output flow for the Vera terminal app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from vera.contracts.events import EventEnvelope
from vera.contracts.skills import SkillSelection, SkillSummary
from vera.contracts.streaming import RuntimeOutput, StreamFrame
from vera.presentation.projector import AppendBlock, UpdateBlock
from vera.presentation.timeline import BlockKind
from vera.session.actions import ExecuteSlashCommand
from vera.session.models import SessionStatus
from vera.terminal.bridge import RuntimeOutputReceived, WorkerStopped
from vera.terminal.widgets.completions import CompletionList
from vera.terminal.widgets.composer import PromptComposer
from vera.terminal.widgets.skill_picker import SkillPicker, build_skill_picker_rows
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline

if TYPE_CHECKING:
    from vera.terminal.app import VeraTerminalApp

_SKILL_NOTICE_PREFIX = "已选择 "


def _skill_selected_notice(selection: SkillSelection) -> str:
    version = selection.version or "版本未知"
    return f"{_SKILL_NOTICE_PREFIX}{selection.skill_id} · {version}，等待下一次任务"


def on_runtime_output_received(host: VeraTerminalApp, message: RuntimeOutputReceived) -> None:
    output = message.output
    sequence = getattr(output, "sequence", None)
    if isinstance(sequence, int):
        host.received_sequences.append(sequence)
    if isinstance(output, EventEnvelope):
        host._apply_session_chrome(output)
        if output.type == "session.status":
            host._session_status = SessionStatus.model_validate(output.payload)
            host._refresh_chrome()
    host.activity.apply(output)
    host._sync_activity()
    if isinstance(output, EventEnvelope):
        if output.type == "session.closed":
            host.exit(0)
            return
        if output.type == "session.message" and output.payload.get("clear_display"):
            host._clear_timeline_display()
            text = str(output.payload.get("text", "")).strip()
            if text:
                status = host._status_line()
                if status is not None:
                    status.set_status(text)
            host._focus_composer_unless_approval()
            return
    timeline = host.query_one(ConversationTimeline)
    if isinstance(output, EventEnvelope) and output.type in {
        "run.started",
        "approval.required",
        "run.failed",
        "run.cancelled",
    }:
        timeline.finish_reveal()
    mutations = host.projector.apply(output)
    if isinstance(output, EventEnvelope) and output.type == "run.completed":
        # The retained Done row replaces the generic completion status card.
        mutations = tuple(
            item
            for item in mutations
            if not isinstance(item, (AppendBlock, UpdateBlock))
            or item.block.kind is not BlockKind.STATUS
        )
    if isinstance(output, StreamFrame) or (
        isinstance(output, EventEnvelope) and output.type == "assistant.message"
    ):
        for item in mutations:
            if (
                isinstance(item, (AppendBlock, UpdateBlock))
                and item.block.kind is BlockKind.ASSISTANT
            ):
                timeline.queue_assistant(item.block)
            else:
                timeline.apply((item,))
    else:
        timeline.apply(mutations)
    if isinstance(output, EventEnvelope) and output.type in {
        "run.completed",
        "run.failed",
        "run.cancelled",
    }:
        outcome = "done" if output.type == "run.completed" else output.type.removeprefix("run.")
        timeline.mark_outcome(output.run_id, outcome)
    host._sync_activity()
    if isinstance(output, EventEnvelope) and output.type in {
        "approval.resolved",
        "approval.expired",
        "approval.invalidated",
        "run.completed",
        "run.failed",
        "run.cancelled",
    }:
        host._focus_composer_unless_approval()
    pending = timeline.pending_update_count
    status = host._status_line()
    if status is not None:
        status.set_pending(pending)
    if isinstance(output, EventEnvelope) and output.type == "session.message":
        message_text = output.payload.get("text")
        if isinstance(message_text, str) and message_text.strip():
            timeline = host.query_one(ConversationTimeline)
            if timeline.follow_tail:
                timeline.return_to_tail()
            host._focus_composer_unless_approval()
    if isinstance(output, EventEnvelope):
        if output.type == "skill.listed":
            present_skill_list(host, output, request_id=message.request_id)
        elif output.type == "skill.selection.changed":
            confirm_skill_selection(host, output, request_id=message.request_id)
            sync_skill_notice(host, output)


def present_skill_list(
    host: VeraTerminalApp, output: EventEnvelope, *, request_id: str | None
) -> None:
    if request_id is None or request_id != host._skill_list_request_id:
        return
    host._skill_list_request_id = None
    if host.controller.active_run_id is not None or host.controller.pending_approval_id is not None:
        return
    picker = host.query_one(SkillPicker)
    items = output.payload.get("items")
    if not isinstance(items, list):
        picker.close()
        host.query_one(VeraStatusLine).set_status("Skill 列表数据无效")
        return
    try:
        summaries = tuple(SkillSummary.model_validate(item) for item in items)
    except ValidationError:
        picker.close()
        host.query_one(VeraStatusLine).set_status("Skill 列表数据无效")
        return
    rows = build_skill_picker_rows(
        summaries,
        selected_skill_id=host.controller.snapshot().skill_selection.skill_id,
    )
    host.query_one(CompletionList).hide()
    picker.open(rows)
    host._open_skill_list_request_id = request_id


def confirm_skill_selection(
    host: VeraTerminalApp, output: EventEnvelope, *, request_id: str | None
) -> None:
    picker = host.query_one(SkillPicker)
    if (
        not picker.display
        or picker.pending_skill_id is None
        or request_id is None
        or request_id != host._skill_use_request_id
    ):
        return
    host._skill_use_request_id = None
    try:
        selection = SkillSelection.model_validate(output.payload["selection"])
    except (KeyError, ValidationError):
        picker.close()
        host.query_one(VeraStatusLine).set_status("Skill 选择结果无效")
        host.query_one(PromptComposer).focus()
        return
    if selection.status == "selected" and selection.skill_id == picker.pending_skill_id:
        picker.close()
        host.query_one(PromptComposer).focus()
        return
    picker.reject(
        selection.reason_codes[0] if selection.reason_codes else "skill_selection_mismatch"
    )


def sync_skill_notice(host: VeraTerminalApp, output: EventEnvelope) -> None:
    status = host._status_line()
    if status is None:
        return
    try:
        selection = SkillSelection.model_validate(output.payload["selection"])
    except (KeyError, ValidationError):
        return
    if selection.status == "selected" and selection.skill_id:
        status.set_status(_skill_selected_notice(selection))
    elif status.notice.startswith(_SKILL_NOTICE_PREFIX):
        status.set_status("")


def on_skill_picker_chosen(host: VeraTerminalApp, message: SkillPicker.Chosen) -> None:
    host._skill_use_request_id = host.bridge.submit(
        ExecuteSlashCommand(raw=f"/skills use {message.skill_id}")
    )


def append_output(host: VeraTerminalApp, output: RuntimeOutput) -> None:
    mutations = host.projector.apply(output)
    host.query_one(ConversationTimeline).apply(mutations)


def on_worker_stopped(host: VeraTerminalApp, message: WorkerStopped) -> None:
    picker = host.query_one(SkillPicker)
    if (
        picker.display
        and host._skill_use_request_id is not None
        and message.request_id == host._skill_use_request_id
    ):
        host._skill_use_request_id = None
        if message.reason_code.startswith("worker_failed"):
            picker.close()
            host.query_one(VeraStatusLine).set_status("Skill 操作失败，请重新运行 /skills")
        elif message.reason_code == "completed":
            picker.close()
            host.query_one(VeraStatusLine).set_status("Skill 选择确认缺失，请重新运行 /skills")
    elif (
        picker.display
        and host._open_skill_list_request_id is not None
        and message.request_id == host._open_skill_list_request_id
        and message.reason_code.startswith("worker_failed")
    ):
        picker.close()
        host.query_one(VeraStatusLine).set_status("Skill 操作失败，请重新运行 /skills")
    if (
        host._open_skill_list_request_id is not None
        and message.request_id == host._open_skill_list_request_id
    ):
        host._open_skill_list_request_id = None
    if message.reason_code.startswith("worker_failed"):
        label = "Worker 失败；可使用 /help 或 --plain"
        host.activity.set_failed(label)
        host._sync_activity()
        if host._session_status is not None:
            host._refresh_chrome()
    elif host.activity.current.active:
        host._sync_activity()
    host._focus_composer_unless_approval()


def apply_session_chrome(host: VeraTerminalApp, output: EventEnvelope) -> None:
    status = host._status_line()
    if status is None:
        return
    if output.type == "session.prompt_queued":
        status.set_status("已排队下一条输入 · Ctrl+U 撤销")
        return
    if output.type == "session.prompt_queue_cleared":
        status.set_status("已撤销排队输入")
        return
    if output.type == "session.prompt_queue_flushed":
        status.set_status("正在提交排队输入")
        return
    if output.type == "session.editor_preview":
        argv = output.payload.get("argv", [])
        rendered = " ".join(str(part) for part in argv) if isinstance(argv, list) else ""
        status.set_status(f"将运行：{rendered}。再次 Ctrl+G 确认")
        host._editor_preview_pending = True
        return
    if output.type == "session.editor_closed":
        text = output.payload.get("text")
        if output.payload.get("changed") and isinstance(text, str):
            host.query_one(PromptComposer).restore_draft(text)
        return
    if output.type == "session.theme":
        theme = output.payload.get("theme")
        if isinstance(theme, str):
            host._apply_theme(theme)
        text = output.payload.get("text")
        if isinstance(text, str) and text.strip():
            status.set_status(text.splitlines()[0])
        elif isinstance(theme, str):
            status.set_status(f"当前主题：{theme}")
        return
    if output.type == "session.action_rejected":
        message = output.payload.get("message")
        if isinstance(message, str) and message:
            status.set_status(message)
