"""Textual application shell for Vera terminal UI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.control import Control
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Resize
from textual.geometry import Size
from textual.widgets import Static

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.presentation.activity import ActivityPresenter
from vera.presentation.projector import TimelineProjector
from vera.session.controller import SessionController
from vera.session.models import SessionStatus
from vera.terminal import input_actions, layout_flow, output_flow
from vera.terminal.alt_enter import install_alt_enter_mapping
from vera.terminal.animation import AnimationClock
from vera.terminal.bridge import RuntimeOutputReceived, TerminalBridge, WorkerStopped
from vera.terminal.capabilities import detect_display_capabilities
from vera.terminal.input_actions import _mention_prefix  # noqa: F401
from vera.terminal.widgets.approval import ApprovalBlockWidget, ApprovalSelected
from vera.terminal.widgets.blocks import TimelineBlockWidget
from vera.terminal.widgets.completions import CompletionList
from vera.terminal.widgets.composer import ComposerBar, PromptComposer, PromptSubmitted
from vera.terminal.widgets.header import VeraHeader
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline
from vera.terminal.widgets.user_sticky import UserStickyBar
from vera.terminal.widgets.welcome import VeraWelcome
from vera.terminal.widgets.work_rail import VeraWorkRail

install_alt_enter_mapping()

_RESIZE_CLEAR = Control.clear().segment.text + Control.home().segment.text


class VeraTerminalApp(App[int]):
    """Fullscreen Textual shell; Core access only via SessionController."""

    CSS_PATH = "theme.tcss"
    MINIMUM_SIZE = Size(60, 16)
    TITLE = "Vera"
    BINDINGS = [
        Binding("escape", "escape", "Cancel", show=False, priority=True),
        ("ctrl+c", "cancel_or_clear", "Cancel"),
        ("ctrl+d", "exit_if_idle", "Exit"),
        ("ctrl+g", "open_editor", "Editor"),
        ("ctrl+u", "clear_composer_or_queue", "Clear"),
        ("ctrl+shift+c", "copy_text", "Copy"),
        ("cmd+c", "copy_text", "Copy"),
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
        from vera.terminal.theme import VERA_THEMES

        for theme in VERA_THEMES:
            self.register_theme(theme)
        self.theme = "default"
        self.controller = controller
        self.workspace = workspace
        self.model_profile = model_profile
        config_animations = getattr(controller.dependencies.config, "ui", None)
        default_animations = True if config_animations is None else config_animations.animations
        self.display_capabilities = detect_display_capabilities(
            animations_config=default_animations
        )
        self.animations = self.display_capabilities.animations if animations is None else animations
        if os.environ.get("VERA_NO_ANIMATIONS", "") == "1":
            self.animations = False
        self.bridge = TerminalBridge(self, controller)
        self.projector = TimelineProjector()
        self.activity = ActivityPresenter()
        self.animation = AnimationClock(enabled=self.animations)
        self.received_sequences: list[int] = []
        self.submitted: list[str] = []
        self._editor_preview_pending = False
        self._welcome_expanded = True
        self._session_status: SessionStatus | None = None
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
        yield VeraWelcome(id="welcome")
        yield UserStickyBar(id="user-sticky")
        yield ConversationTimeline(id="timeline")
        yield CompletionList(id="completions")
        yield VeraWorkRail(id="work-rail")
        yield ComposerBar(id="composer-bar")
        yield VeraStatusLine(id="status-line")
        yield self._too_small

    def on_mount(self) -> None:
        self.query_one(PromptComposer).focus()
        self.query_one(PromptComposer).sync_multiline_layout()
        self._apply_size(self.size)
        if not self.display_capabilities.color:
            self._apply_theme("no-color")
        else:
            self._apply_theme("default")
        self.set_interval(0.1, self._tick_status)
        self.set_interval(0.05, self._tick_wave)
        self._present_bootstrap()

    def _present_bootstrap(self) -> None:
        layout_flow.present_bootstrap(self)

    def on_resize(self, event: Resize) -> None:
        layout_flow.on_resize(self, event)

    def on_unmount(self) -> None:
        layout_flow.on_unmount(self)

    def _unicode(self) -> bool:
        return layout_flow.unicode(self)

    def _apply_size(self, size: Size) -> None:
        layout_flow.apply_size(self, size)

    def _repaint_after_resize(self) -> None:
        layout_flow.repaint_after_resize(self)

    def _collapse_welcome(self) -> None:
        layout_flow.collapse_welcome(self)

    def submit_composer(self) -> None:
        input_actions.submit_composer(self)

    def on_text_area_changed(self, event) -> None:  # type: ignore[no-untyped-def]
        input_actions.on_text_area_changed(self, event)

    def _refresh_completions(self, text: str) -> None:
        input_actions.refresh_completions(self, text)

    def on_prompt_submitted(self, message: PromptSubmitted) -> None:
        input_actions.on_prompt_submitted(self, message)

    def on_approval_selected(self, message: ApprovalSelected) -> None:
        input_actions.on_approval_selected(self, message)

    def _status_line(self) -> VeraStatusLine | None:
        return layout_flow.status_line(self)

    def _work_rail(self) -> VeraWorkRail | None:
        return layout_flow.work_rail(self)

    def _sync_activity(self) -> None:
        layout_flow.sync_activity(self)

    def on_runtime_output_received(self, message: RuntimeOutputReceived) -> None:
        output_flow.on_runtime_output_received(self, message)

    def block(self, block_id: str) -> TimelineBlockWidget:
        return self.query_one(ConversationTimeline).block_widget(block_id)

    def append_output(self, output: RuntimeOutput) -> None:
        output_flow.append_output(self, output)

    def on_worker_stopped(self, message: WorkerStopped) -> None:
        output_flow.on_worker_stopped(self, message)

    def action_escape(self) -> None:
        input_actions.action_escape(self)

    def action_cancel_or_clear(self) -> None:
        input_actions.action_cancel_or_clear(self)

    def action_clear_composer_or_queue(self) -> None:
        input_actions.action_clear_composer_or_queue(self)

    def action_open_editor(self) -> None:
        input_actions.action_open_editor(self)

    def _apply_session_chrome(self, output: EventEnvelope) -> None:
        output_flow.apply_session_chrome(self, output)

    def _apply_theme(self, name: str) -> None:
        layout_flow.apply_theme(self, name)

    def action_exit_if_idle(self) -> None:
        input_actions.action_exit_if_idle(self)

    def copy_to_clipboard(self, text: str) -> None:
        super().copy_to_clipboard(text)
        if sys.platform != "darwin" or not text:
            return
        try:
            subprocess.run(
                ["/usr/bin/pbcopy"],
                input=text.encode("utf-8"),
                check=False,
            )
        except OSError:
            return

    def on_text_selected(self) -> None:
        input_actions.on_text_selected(self)

    def action_copy_text(self) -> None:
        input_actions.action_copy_text(self)

    def _last_copyable_text(self) -> str:
        return input_actions.last_copyable_text(self)

    def action_return_to_tail(self) -> None:
        input_actions.action_return_to_tail(self)

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        input_actions.on_key(self, event)

    def on_mouse_scroll_up(self, event) -> None:  # type: ignore[no-untyped-def]
        input_actions.on_mouse_scroll_up(self, event)

    def on_mouse_scroll_down(self, event) -> None:  # type: ignore[no-untyped-def]
        input_actions.on_mouse_scroll_down(self, event)

    def _clear_timeline_display(self) -> None:
        input_actions.clear_timeline_display(self)

    def _focus_composer_unless_approval(self) -> None:
        input_actions.focus_composer_unless_approval(self)

    def _cycle_approval_focus(self, *, reverse: bool) -> bool:
        return input_actions.cycle_approval_focus(self, reverse=reverse)

    def _active_approval_widget(self) -> ApprovalBlockWidget | None:
        return input_actions.active_approval_widget(self)

    def _sync_sticky_offset(self) -> None:
        layout_flow.sync_sticky_offset(self)

    def _refresh_chrome(self) -> None:
        layout_flow.refresh_chrome(self)

    def _tick_status(self) -> None:
        layout_flow.tick_status(self)

    def _tick_wave(self) -> None:
        layout_flow.tick_wave(self)


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
