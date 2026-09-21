"""Runtime-output flow for the Vera terminal app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.presentation.projector import UpdateBlock
from vera.session.models import SessionStatus
from vera.terminal.bridge import RuntimeOutputReceived, WorkerStopped
from vera.terminal.widgets.composer import PromptComposer
from vera.terminal.widgets.timeline import ConversationTimeline

if TYPE_CHECKING:
    from vera.terminal.app import VeraTerminalApp


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
    mutations = host.projector.apply(output)
    timeline = host.query_one(ConversationTimeline)
    streaming_updates = [
        item.block
        for item in mutations
        if isinstance(item, UpdateBlock) and item.block.kind.value == "assistant"
    ]
    if streaming_updates and all(isinstance(item, UpdateBlock) for item in mutations):
        for block in streaming_updates:
            timeline.apply_streaming_update(block)
    else:
        timeline.apply(mutations)
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


def append_output(host: VeraTerminalApp, output: RuntimeOutput) -> None:
    mutations = host.projector.apply(output)
    host.query_one(ConversationTimeline).apply(mutations)


def on_worker_stopped(host: VeraTerminalApp, message: WorkerStopped) -> None:
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
