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
    CloseSession,
    ExecuteSlashCommand,
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

    def on_prompt_submitted(self, message: PromptSubmitted) -> None:
        text = message.text
        self.submitted.append(text)
        if text.startswith("/"):
            self.bridge.submit(ExecuteSlashCommand(raw=text))
        else:
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
        self.query_one(VeraStatusLine).set_status("输入 /exit 或 Ctrl+D 退出")

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
