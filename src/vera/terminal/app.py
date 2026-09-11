"""Textual application shell for Vera terminal UI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.events import Resize
from textual.geometry import Size
from textual.widgets import Static

from vera.session.actions import CancelActiveRun, ExecuteSlashCommand, SubmitPrompt
from vera.session.controller import SessionController
from vera.terminal.bridge import RuntimeOutputReceived, TerminalBridge, WorkerStopped
from vera.terminal.widgets.composer import PromptComposer
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
    ]

    def __init__(
        self,
        controller: SessionController,
        workspace: Path,
        model_profile: str,
        *,
        animations: bool = True,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.workspace = workspace
        self.model_profile = model_profile
        self.animations = animations
        self.bridge = TerminalBridge(self, controller)
        self.received_sequences: list[int] = []
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
        yield PromptComposer(id="composer")
        yield VeraStatusLine(id="status-line")
        yield self._too_small

    def on_mount(self) -> None:
        self.query_one(PromptComposer).focus()
        self._apply_size(self.size)

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
        composer = self.query_one(PromptComposer)
        text = composer.text.strip()
        if not text:
            return
        composer.load_text("")
        if text.startswith("/"):
            self.bridge.submit(ExecuteSlashCommand(raw=text))
        else:
            self.bridge.submit(SubmitPrompt(text=text))

    def on_runtime_output_received(self, message: RuntimeOutputReceived) -> None:
        output = message.output
        sequence = getattr(output, "sequence", None)
        if isinstance(sequence, int):
            self.received_sequences.append(sequence)
        status = self.query_one(VeraStatusLine)
        kind = getattr(output, "type", type(output).__name__)
        status.set_status(f"收到 {kind}")

    def on_worker_stopped(self, message: WorkerStopped) -> None:
        status = self.query_one(VeraStatusLine)
        if message.reason_code.startswith("worker_failed"):
            status.set_status("Worker 失败；可使用 /help 或 --plain")
        else:
            status.set_status("就绪 · Esc/Ctrl-C 取消 · /help")

    def action_cancel_or_clear(self) -> None:
        composer = self.query_one(PromptComposer)
        if self.controller.active_run_id is not None:
            self.bridge.submit(CancelActiveRun(run_id=self.controller.active_run_id))
            return
        if composer.text:
            composer.load_text("")
            return
        self.query_one(VeraStatusLine).set_status("输入 /exit 或 Ctrl+D 退出")


def launch_tui(
    controller: SessionController,
    workspace: Path,
    model_profile: str,
    *,
    animations: bool = True,
) -> int:
    app = VeraTerminalApp(controller, workspace, model_profile, animations=animations)
    result = app.run()
    return int(result or 0)
