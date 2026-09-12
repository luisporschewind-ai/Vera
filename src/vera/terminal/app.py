"""Textual application shell for Vera terminal UI."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.events import Resize
from textual.geometry import Size
from textual.widgets import Static

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.presentation.activity import ActivityPresenter
from vera.presentation.projector import TimelineProjector, UpdateBlock
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.session.controller import SessionController
from vera.terminal.animation import AnimationClock
from vera.terminal.bridge import RuntimeOutputReceived, TerminalBridge, WorkerStopped
from vera.terminal.widgets.approval import ApprovalSelected
from vera.terminal.widgets.blocks import TimelineBlockWidget
from vera.terminal.widgets.completions import CompletionList
from vera.terminal.widgets.composer import PromptComposer, PromptSubmitted
from vera.terminal.widgets.header import VeraHeader
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline


class VeraTerminalApp(App[int]):
    """Fullscreen Textual shell; Core access only via SessionController."""

    CSS_PATH = "theme.tcss"
    MINIMUM_SIZE = Size(60, 16)
    TITLE = "Vera"
    BINDINGS = [
        ("ctrl+c", "cancel_or_clear", "Cancel"),
        ("ctrl+d", "exit_if_idle", "Exit"),
        ("ctrl+g", "open_editor", "Editor"),
        ("ctrl+u", "clear_composer_or_queue", "Clear"),
        ("end", "return_to_tail", "End"),
    ]

    def __init__(
        self,
        controller: SessionController,
        workspace: Path,
        model_profile: str,
        *,
        animations: bool | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.workspace = workspace
        self.model_profile = model_profile
        env_disabled = os.environ.get("VERA_NO_ANIMATIONS", "") == "1"
        config_animations = getattr(controller.dependencies.config, "ui", None)
        default_animations = True if config_animations is None else config_animations.animations
        self.animations = default_animations if animations is None else animations
        if env_disabled:
            self.animations = False
        self.bridge = TerminalBridge(self, controller)
        self.projector = TimelineProjector()
        self.activity = ActivityPresenter()
        self.animation = AnimationClock(enabled=self.animations)
        self.received_sequences: list[int] = []
        self.submitted: list[str] = []
        self._editor_preview_pending = False
        self._too_small = Static(
            "终端太小：请调整到至少 60×16",
            id="terminal-too-small",
        )

    def compose(self) -> ComposeResult:
        yield VeraHeader(
            model_profile=self.model_profile,
            workspace_label=str(self.workspace),
            id="header",
        )
        yield ConversationTimeline(id="timeline")
        yield CompletionList(id="completions")
        yield PromptComposer(id="composer")
        yield VeraStatusLine(id="status-line")
        yield self._too_small

    def on_mount(self) -> None:
        self.query_one(PromptComposer).focus()
        self._apply_size(self.size)
        self.set_interval(0.1, self._tick_status)

    def on_resize(self, event: Resize) -> None:
        self._apply_size(event.size)

    def on_unmount(self) -> None:
        self.bridge.cancel_workers()

    def _apply_size(self, size: Size) -> None:
        too_small = size.width < self.MINIMUM_SIZE.width or size.height < self.MINIMUM_SIZE.height
        banner = self.query_one("#terminal-too-small", Static)
        banner.display = too_small
        header = self.query_one(VeraHeader)
        header.set_narrow(size.width < 80)
        if not too_small:
            self.query_one(PromptComposer).focus()

    def submit_composer(self) -> None:
        self.query_one(PromptComposer).submit()

    def on_text_area_changed(self, event) -> None:  # type: ignore[no-untyped-def]
        composer = self.query_one(PromptComposer)
        if event.text_area is not composer:
            return
        self._refresh_completions(composer.text)

    def _refresh_completions(self, text: str) -> None:
        completions = self.query_one(CompletionList)
        stripped = text.lstrip()
        if stripped.startswith("/"):
            token = stripped.split()[0] if stripped.split() else stripped
            completions.update_for_prefix(token, self.controller.snapshot())
            return
        mention = _mention_prefix(text)
        if mention is not None:
            completions.update_for_path(
                mention,
                self.workspace,
                state_dir=self.controller.dependencies.config.state_dir,
            )
            return
        completions.hide()

    def on_prompt_submitted(self, message: PromptSubmitted) -> None:
        text = message.text
        self.submitted.append(text)
        if text.startswith("/"):
            self.bridge.submit(ExecuteSlashCommand(raw=text))
            return
        composer = self.query_one(PromptComposer)
        if self.controller.pending_approval_id is not None:
            composer.load_text(text)
            self.query_one(VeraStatusLine).set_status("等待审批时不能排队下一条输入")
            return
        if self.controller.active_run_id is not None:
            if self.controller.queued_prompt is not None:
                composer.load_text(text)
                self.query_one(VeraStatusLine).set_status("已有一条排队输入，请先撤销再替换")
                return
            self.bridge.submit(QueuePrompt(text=text))
            return
        self.bridge.submit(SubmitPrompt(text=text))

    def on_approval_selected(self, message: ApprovalSelected) -> None:
        self.bridge.submit(
            ResolveSessionApproval(
                approval_id=message.approval_id,
                decision=message.decision,  # type: ignore[arg-type]
            )
        )

    def on_runtime_output_received(self, message: RuntimeOutputReceived) -> None:
        output = message.output
        sequence = getattr(output, "sequence", None)
        if isinstance(sequence, int):
            self.received_sequences.append(sequence)
        if isinstance(output, EventEnvelope):
            self._apply_session_chrome(output)
            state = self.activity.apply(output)
            self.query_one(VeraStatusLine).set_activity(state, self.animation.frame())
        mutations = self.projector.apply(output)
        timeline = self.query_one(ConversationTimeline)
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
        pending = timeline.pending_update_count
        if pending:
            self.query_one(VeraStatusLine).set_pending(pending)

    def block(self, block_id: str) -> TimelineBlockWidget:
        return self.query_one(ConversationTimeline).block_widget(block_id)

    def append_output(self, output: RuntimeOutput) -> None:
        mutations = self.projector.apply(output)
        self.query_one(ConversationTimeline).apply(mutations)

    def on_worker_stopped(self, message: WorkerStopped) -> None:
        status = self.query_one(VeraStatusLine)
        if message.reason_code.startswith("worker_failed"):
            status.set_status("Worker 失败；可使用 /help 或 --plain")
        else:
            status.set_activity(self.activity.current, self.animation.frame())

    def action_cancel_or_clear(self) -> None:
        composer = self.query_one(PromptComposer)
        if self.controller.active_run_id is not None:
            self.bridge.submit(CancelActiveRun(run_id=self.controller.active_run_id))
            return
        if composer.text.strip():
            composer.clear_input()
            return
        if self.controller.queued_prompt is not None:
            self.bridge.submit(ClearQueuedPrompt())
            return
        self.query_one(VeraStatusLine).set_status("输入 /exit 或 Ctrl+D 退出")

    def action_clear_composer_or_queue(self) -> None:
        composer = self.query_one(PromptComposer)
        if composer.text.strip():
            composer.clear_input()
            return
        if self.controller.queued_prompt is not None:
            self.bridge.submit(ClearQueuedPrompt())

    def action_open_editor(self) -> None:
        composer = self.query_one(PromptComposer)
        if self._editor_preview_pending:
            self.bridge.submit(ConfirmExternalEditor(accept=True))
            self._editor_preview_pending = False
        self.bridge.submit(OpenExternalEditor(text=composer.text))

    def _apply_session_chrome(self, output: EventEnvelope) -> None:
        status = self.query_one(VeraStatusLine)
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
            self._editor_preview_pending = True
            return
        if output.type == "session.editor_closed":
            text = output.payload.get("text")
            if output.payload.get("changed") and isinstance(text, str):
                self.query_one(PromptComposer).load_text(text)
            return
        if output.type == "session.theme":
            theme = output.payload.get("theme")
            if isinstance(theme, str):
                self._apply_theme(theme)
            return
        if output.type == "session.action_rejected":
            message = output.payload.get("message")
            if isinstance(message, str) and message:
                status.set_status(message)

    def _apply_theme(self, name: str) -> None:
        from vera.terminal.theme import THEME_NAMES, theme_class

        for item in THEME_NAMES:
            self.screen.remove_class(theme_class(item))
        if name in THEME_NAMES:
            self.screen.add_class(theme_class(name))

    def action_exit_if_idle(self) -> None:
        composer = self.query_one(PromptComposer)
        if self.controller.active_run_id is not None or composer.text.strip():
            return
        # Close synchronously so pending approvals become cancel before UI teardown.
        tuple(self.controller.dispatch(CloseSession()))
        self.exit(0)

    def action_return_to_tail(self) -> None:
        self.query_one(ConversationTimeline).return_to_tail()

    def _tick_status(self) -> None:
        if not self.activity.current.active:
            return
        self.query_one(VeraStatusLine).set_activity(
            self.activity.current,
            self.animation.frame(),
        )


def _mention_prefix(text: str) -> str | None:
    index = text.rfind("@")
    if index < 0:
        return None
    fragment = text[index + 1 :]
    if "\n" in fragment:
        return None
    return fragment


def launch_tui(
    controller: SessionController,
    workspace: Path,
    model_profile: str,
    *,
    animations: bool | None = None,
) -> int:
    app = VeraTerminalApp(controller, workspace, model_profile, animations=animations)
    result = app.run()
    return int(result or 0)
