"""Textual application shell for Vera terminal UI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.events import Resize
from textual.geometry import Size
from textual.widgets import Static

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.presentation.activity import ActivityPresenter
from vera.presentation.projector import TimelineProjector, UpdateBlock
from vera.presentation.timeline import BlockKind
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
from vera.session.models import SessionStatus
from vera.terminal.alt_enter import install_alt_enter_mapping
from vera.terminal.animation import AnimationClock
from vera.terminal.bridge import RuntimeOutputReceived, TerminalBridge, WorkerStopped
from vera.terminal.capabilities import detect_display_capabilities
from vera.terminal.widgets.approval import ApprovalBlockWidget, ApprovalSelected
from vera.terminal.widgets.blocks import TimelineBlockWidget
from vera.terminal.widgets.completions import CompletionList
from vera.terminal.widgets.composer import (
    ComposerBar,
    PromptComposer,
    PromptSubmitted,
    select_composer_prompt,
)
from vera.terminal.widgets.header import VeraHeader
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline
from vera.terminal.widgets.user_sticky import UserStickyBar
from vera.terminal.widgets.welcome import VeraWelcome

install_alt_enter_mapping()


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
        self._present_bootstrap()

    def _present_bootstrap(self) -> None:
        for event in self.controller.bootstrap_events():
            self.on_runtime_output_received(RuntimeOutputReceived(event))

    def on_resize(self, event: Resize) -> None:
        self._apply_size(event.size)

    def on_unmount(self) -> None:
        self.bridge.cancel_workers()

    def _unicode(self) -> bool:
        term = self.display_capabilities.term.strip().lower()
        return term not in {"", "dumb", "unavailable"}

    def _apply_size(self, size: Size) -> None:
        too_small = size.width < self.MINIMUM_SIZE.width or size.height < self.MINIMUM_SIZE.height
        try:
            banner = self.query_one("#terminal-too-small", Static)
            header = self.query_one(VeraHeader)
        except NoMatches:
            return
        banner.display = too_small
        header.apply_geometry(columns=size.width, rows=size.height, unicode=self._unicode())
        status = self._status_line()
        if status is not None:
            status.set_geometry(columns=size.width, unicode=self._unicode())
        if self._session_status is not None:
            self._refresh_chrome()
        else:
            self._sync_sticky_offset()
        if not too_small:
            try:
                self.query_one(PromptComposer).focus()
            except NoMatches:
                return
        self.refresh()

    def submit_composer(self) -> None:
        self.query_one(PromptComposer).submit()

    def on_text_area_changed(self, event) -> None:  # type: ignore[no-untyped-def]
        try:
            composer = self.query_one(PromptComposer)
        except Exception:
            return
        if event.text_area is not composer:
            return
        composer.sync_multiline_layout()
        self._refresh_completions(composer.text)

    def _refresh_completions(self, text: str) -> None:
        completions = self.query_one(CompletionList)
        snapshot = self.controller.snapshot()
        if completions.update_for_input(text, snapshot):
            if completions.needs_restore and completions.last_query and "@" not in text:
                composer = self.query_one(PromptComposer)
                if composer.text != completions.last_query:
                    composer.load_text(completions.last_query)
                    composer.cursor_location = (0, len(completions.last_query))
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
        self.query_one(CompletionList).hide()
        self.query_one(ConversationTimeline).return_to_tail()
        self._focus_composer_unless_approval()
        text = message.text
        self.submitted.append(text)
        if text.startswith("/"):
            self.bridge.submit(ExecuteSlashCommand(raw=text))
            return
        composer = self.query_one(PromptComposer)
        if self.controller.pending_approval_id is not None:
            composer.restore_draft(text)
            self.query_one(VeraStatusLine).set_status("等待审批时不能排队下一条输入")
            return
        if self.controller.active_run_id is not None:
            if self.controller.queued_prompt is not None:
                composer.restore_draft(text)
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

    def _status_line(self) -> VeraStatusLine | None:
        try:
            return self.query_one(VeraStatusLine)
        except NoMatches:
            return None

    def on_runtime_output_received(self, message: RuntimeOutputReceived) -> None:
        output = message.output
        sequence = getattr(output, "sequence", None)
        if isinstance(sequence, int):
            self.received_sequences.append(sequence)
        if isinstance(output, EventEnvelope):
            self._apply_session_chrome(output)
            if output.type == "session.status":
                self._session_status = SessionStatus.model_validate(output.payload)
                self._refresh_chrome()
            state = self.activity.apply(output)
            status = self._status_line()
            if status is not None:
                status.set_activity(state, self.animation.frame())
            if output.type == "session.closed":
                self.exit(0)
                return
            if output.type == "session.message" and output.payload.get("clear_display"):
                self._clear_timeline_display()
                text = str(output.payload.get("text", "")).strip()
                if text:
                    status = self._status_line()
                    if status is not None:
                        status.set_status(text)
                self._focus_composer_unless_approval()
                return
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
        if isinstance(output, EventEnvelope) and output.type in {
            "approval.resolved",
            "approval.expired",
            "approval.invalidated",
            "run.completed",
            "run.failed",
            "run.cancelled",
        }:
            self._focus_composer_unless_approval()
        pending = timeline.pending_update_count
        status = self._status_line()
        if status is not None:
            status.set_pending(pending)
        if isinstance(output, EventEnvelope) and output.type == "session.message":
            message_text = output.payload.get("text")
            if isinstance(message_text, str) and message_text.strip():
                status = self._status_line()
                if status is not None:
                    status.set_status(message_text)
                timeline = self.query_one(ConversationTimeline)
                if timeline.follow_tail:
                    timeline.return_to_tail()
                self._focus_composer_unless_approval()

    def block(self, block_id: str) -> TimelineBlockWidget:
        return self.query_one(ConversationTimeline).block_widget(block_id)

    def append_output(self, output: RuntimeOutput) -> None:
        mutations = self.projector.apply(output)
        self.query_one(ConversationTimeline).apply(mutations)

    def on_worker_stopped(self, message: WorkerStopped) -> None:
        status = self._status_line()
        if status is None:
            return
        if message.reason_code.startswith("worker_failed"):
            label = "Worker 失败；可使用 /help 或 --plain"
            self.activity.set_failed(label)
            status.set_status(label)
            if self._session_status is not None:
                self._refresh_chrome()
        elif self.activity.current.active:
            status.set_activity(self.activity.current, self.animation.frame())
        self._focus_composer_unless_approval()

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
        status = self._status_line()
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
            self._editor_preview_pending = True
            return
        if output.type == "session.editor_closed":
            text = output.payload.get("text")
            if output.payload.get("changed") and isinstance(text, str):
                self.query_one(PromptComposer).restore_draft(text)
            return
        if output.type == "session.theme":
            theme = output.payload.get("theme")
            if isinstance(theme, str):
                self._apply_theme(theme)
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

    def _apply_theme(self, name: str) -> None:
        from vera.terminal.theme import THEME_NAMES, theme_class

        if name not in THEME_NAMES or name not in self.available_themes:
            return
        previous = self.theme
        self.theme = name
        if previous == name:
            self.refresh_css(animate=False)
        for item in THEME_NAMES:
            active = item == name
            self.set_class(active, theme_class(item))
            self.screen.set_class(active, theme_class(item))
        self.refresh_css(animate=False)
        self.refresh()
        self._sync_sticky_offset()

    def action_exit_if_idle(self) -> None:
        composer = self.query_one(PromptComposer)
        if self.controller.active_run_id is not None or composer.text.strip():
            return
        # Close synchronously so pending approvals become cancel before UI teardown.
        tuple(self.controller.dispatch(CloseSession()))
        self.exit(0)

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
        selected = self.screen.get_selected_text()
        if not selected:
            return
        self.copy_to_clipboard(selected)
        self.query_one(VeraStatusLine).set_status("已复制选中文本")

    def action_copy_text(self) -> None:
        selected = self.screen.get_selected_text()
        text = selected if selected else self._last_copyable_text()
        status = self.query_one(VeraStatusLine)
        if not text:
            status.set_status("没有可复制的文本")
            return
        self.copy_to_clipboard(text)
        status.set_status("已复制选中文本" if selected else "已复制最近一块文本")

    def _last_copyable_text(self) -> str:
        preferred = {
            BlockKind.ERROR,
            BlockKind.DIFF,
            BlockKind.ASSISTANT,
            BlockKind.STATUS,
        }
        for block in reversed(list(self.projector.blocks())):
            if block.kind in preferred and block.body.strip():
                return block.body
        return ""

    def action_return_to_tail(self) -> None:
        self.query_one(ConversationTimeline).return_to_tail()

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key in {"tab", "shift+tab"} and self._cycle_approval_focus(
            reverse=event.key == "shift+tab"
        ):
            event.prevent_default()
            event.stop()
            return
        character = getattr(event, "character", None)
        if not character or not character.isprintable():
            return
        if self.controller.pending_approval_id is not None:
            return
        try:
            composer = self.query_one(PromptComposer)
        except Exception:
            return
        if self.focused is composer:
            return
        composer.focus()
        composer.insert(character)
        event.prevent_default()
        event.stop()

    def on_mouse_scroll_up(self, event) -> None:  # type: ignore[no-untyped-def]
        event.stop()

    def on_mouse_scroll_down(self, event) -> None:  # type: ignore[no-untyped-def]
        event.stop()

    def _clear_timeline_display(self) -> None:
        self.projector.reset()
        self.activity.reset()
        timeline = self.query_one(ConversationTimeline)
        timeline.clear_blocks()
        timeline.pin_home()
        for sticky in self.query(UserStickyBar):
            sticky.hide_message()
        for composer in self.query(PromptComposer):
            composer.prompt_history.clear()
            composer.load_text("")
        self._session_status = self.controller.session_status()
        line = self._status_line()
        if line is not None:
            line.set_pending(0)
        self._refresh_chrome()
        timeline.pin_home()

    def _focus_composer_unless_approval(self) -> None:
        widget = self._active_approval_widget()
        if widget is not None:
            widget.focus_default_action()
            return
        try:
            self.query_one(PromptComposer).focus()
        except Exception:
            return

    def _cycle_approval_focus(self, *, reverse: bool) -> bool:
        widget = self._active_approval_widget()
        if widget is None:
            return False
        return widget.cycle_focus(reverse=reverse)

    def _active_approval_widget(self) -> ApprovalBlockWidget | None:
        if self.controller.pending_approval_id is None:
            return None
        try:
            return next(
                item for item in reversed(list(self.query(ApprovalBlockWidget))) if not item._locked
            )
        except StopIteration:
            return None

    def _sync_sticky_offset(self) -> None:
        try:
            sticky = self.query_one(UserStickyBar)
            bar = self.query_one(ComposerBar)
        except NoMatches:
            return
        columns = self.size.width
        rows = self.size.height
        unicode = self._unicode()
        sticky.styles.margin = (0, 2, 0, 2)
        sticky.apply_geometry(columns=columns, rows=rows, unicode=unicode)
        try:
            bar.set_prompt_glyph(select_composer_prompt(unicode=unicode))
        except NoMatches:
            return

    def _refresh_chrome(self) -> None:
        status = self._session_status
        if status is None:
            return
        try:
            header = self.query_one(VeraHeader)
            welcome = self.query_one(VeraWelcome)
        except NoMatches:
            return
        header.set_session_status(status)
        mark = header.current_mark()
        welcome.set_content(mark, status, columns=self.size.width)
        self._sync_sticky_offset()
        line = self._status_line()
        if line is not None:
            line.apply_session(status, self.activity.current, unread=line._pending)

    def _tick_status(self) -> None:
        if not self.is_running:
            return
        if self._session_status is not None:
            self._refresh_chrome()
            line = self._status_line()
            if line is not None and self.activity.current.active:
                line.set_activity(self.activity.current, self.animation.frame())
            return
        if not self.activity.current.active:
            return
        line = self._status_line()
        if line is not None:
            line.set_activity(self.activity.current, self.animation.frame())


def _mention_prefix(text: str) -> str | None:
    index = text.rfind("@")
    if index < 0:
        return None
    fragment = text[index + 1 :]
    if not fragment:
        return ""
    if any(separator in fragment for separator in ("\n", " ", "\t")):
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
