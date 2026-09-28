"""Input, approval and clipboard flows for the Vera terminal app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.css.query import NoMatches

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
from vera.terminal.widgets.approval import ApprovalBlockWidget, ApprovalSelected
from vera.terminal.widgets.completions import CompletionList
from vera.terminal.widgets.composer import PromptComposer, PromptSubmitted
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.terminal.widgets.timeline import ConversationTimeline
from vera.terminal.widgets.user_sticky import UserStickyBar

if TYPE_CHECKING:
    from vera.terminal.app import VeraTerminalApp


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


def submit_composer(host: VeraTerminalApp) -> None:
    host.query_one(PromptComposer).submit()


def on_text_area_changed(host: VeraTerminalApp, event: Any) -> None:
    try:
        composer = host.query_one(PromptComposer)
    except Exception:
        return
    if event.text_area is not composer:
        return
    composer.sync_multiline_layout()
    host._refresh_completions(composer.text)


def refresh_completions(host: VeraTerminalApp, text: str) -> None:
    completions = host.query_one(CompletionList)
    snapshot = host.controller.snapshot()
    if completions.update_for_input(text, snapshot):
        if completions.needs_restore and completions.last_query and "@" not in text:
            composer = host.query_one(PromptComposer)
            if composer.text != completions.last_query:
                composer.load_text(completions.last_query)
                composer.cursor_location = (0, len(completions.last_query))
        return
    mention = _mention_prefix(text)
    if mention is not None:
        completions.update_for_path(
            mention,
            host.workspace,
            state_dir=host.controller.dependencies.config.state_dir,
        )
        return
    completions.hide()


def on_prompt_submitted(host: VeraTerminalApp, message: PromptSubmitted) -> None:
    host.query_one(CompletionList).hide()
    host.query_one(ConversationTimeline).return_to_tail()
    host._focus_composer_unless_approval()
    text = message.text
    host.submitted.append(text)
    if text.startswith("/"):
        host.bridge.submit(ExecuteSlashCommand(raw=text))
        return
    composer = host.query_one(PromptComposer)
    if host.controller.pending_approval_id is not None:
        composer.restore_draft(text)
        host.query_one(VeraStatusLine).set_status("等待审批时不能排队下一条输入")
        return
    if host.controller.active_run_id is not None:
        if host.controller.queued_prompt is not None:
            composer.restore_draft(text)
            host.query_one(VeraStatusLine).set_status("已有一条排队输入，请先撤销再替换")
            return
        host._collapse_welcome()
        host.bridge.submit(QueuePrompt(text=text))
        return
    host._collapse_welcome()
    host.bridge.submit(SubmitPrompt(text=text))


def on_approval_selected(host: VeraTerminalApp, message: ApprovalSelected) -> None:
    host.bridge.submit(
        ResolveSessionApproval(
            approval_id=message.approval_id,
            decision=message.decision,  # type: ignore[arg-type]
        )
    )


def action_escape(host: VeraTerminalApp) -> None:
    if host.controller.active_run_id is not None:
        host.action_cancel_or_clear()
        return
    try:
        completions = host.query_one(CompletionList)
    except NoMatches:
        return
    if completions.display:
        completions.hide()


def action_cancel_or_clear(host: VeraTerminalApp) -> None:
    composer = host.query_one(PromptComposer)
    if host.controller.active_run_id is not None:
        host.bridge.submit(CancelActiveRun(run_id=host.controller.active_run_id))
        return
    if composer.text.strip():
        composer.clear_input()
        return
    if host.controller.queued_prompt is not None:
        host.bridge.submit(ClearQueuedPrompt())
        return
    host.query_one(VeraStatusLine).set_status("输入 /exit 或 Ctrl+D 退出")


def action_clear_composer_or_queue(host: VeraTerminalApp) -> None:
    composer = host.query_one(PromptComposer)
    if composer.text.strip():
        composer.clear_input()
        return
    if host.controller.queued_prompt is not None:
        host.bridge.submit(ClearQueuedPrompt())


def action_open_editor(host: VeraTerminalApp) -> None:
    composer = host.query_one(PromptComposer)
    if host._editor_preview_pending:
        host.bridge.submit(ConfirmExternalEditor(accept=True))
        host._editor_preview_pending = False
    host.bridge.submit(OpenExternalEditor(text=composer.text))


def action_exit_if_idle(host: VeraTerminalApp) -> None:
    composer = host.query_one(PromptComposer)
    if host.controller.active_run_id is not None or composer.text.strip():
        return
    # Close synchronously so pending approvals become cancel before UI teardown.
    tuple(host.controller.dispatch(CloseSession()))
    host.exit(0)


def on_text_selected(host: VeraTerminalApp) -> None:
    selected = host.screen.get_selected_text()
    if not selected:
        return
    host.copy_to_clipboard(selected)
    host.query_one(VeraStatusLine).set_status("已复制选中文本")


def action_copy_text(host: VeraTerminalApp) -> None:
    selected = host.screen.get_selected_text()
    text = selected if selected else host._last_copyable_text()
    status = host.query_one(VeraStatusLine)
    if not text:
        status.set_status("没有可复制的文本")
        return
    host.copy_to_clipboard(text)
    status.set_status("已复制选中文本" if selected else "已复制最近一块文本")


def last_copyable_text(host: VeraTerminalApp) -> str:
    preferred = {
        BlockKind.ERROR,
        BlockKind.DIFF,
        BlockKind.ASSISTANT,
        BlockKind.STATUS,
    }
    for block in reversed(list(host.projector.blocks())):
        if block.kind in preferred and block.body.strip():
            return block.body
    return ""


def action_return_to_tail(host: VeraTerminalApp) -> None:
    host.query_one(ConversationTimeline).return_to_tail()


def on_key(host: VeraTerminalApp, event: Any) -> None:
    if event.key in {"tab", "shift+tab"} and host._cycle_approval_focus(
        reverse=event.key == "shift+tab"
    ):
        event.prevent_default()
        event.stop()
        return
    character = getattr(event, "character", None)
    if not character or not character.isprintable():
        return
    if host.controller.pending_approval_id is not None:
        return
    try:
        composer = host.query_one(PromptComposer)
    except Exception:
        return
    if host.focused is composer:
        return
    composer.focus()
    composer.insert(character)
    event.prevent_default()
    event.stop()


def on_mouse_scroll_up(host: VeraTerminalApp, event: Any) -> None:
    event.stop()


def on_mouse_scroll_down(host: VeraTerminalApp, event: Any) -> None:
    event.stop()


def clear_timeline_display(host: VeraTerminalApp) -> None:
    host.projector.reset()
    host.activity.reset()
    timeline = host.query_one(ConversationTimeline)
    timeline.clear_blocks()
    timeline.pin_home()
    for sticky in host.query(UserStickyBar):
        sticky.hide_message()
    for composer in host.query(PromptComposer):
        composer.prompt_history.clear()
        composer.load_text("")
    host._session_status = host.controller.session_status()
    line = host._status_line()
    if line is not None:
        line.set_pending(0)
    host._sync_activity()
    host._refresh_chrome()
    timeline.pin_home()


def focus_composer_unless_approval(host: VeraTerminalApp) -> None:
    widget = host._active_approval_widget()
    if widget is not None:
        widget.focus_default_action()
        return
    try:
        host.query_one(PromptComposer).focus()
    except Exception:
        return


def cycle_approval_focus(host: VeraTerminalApp, *, reverse: bool) -> bool:
    widget = host._active_approval_widget()
    if widget is None:
        return False
    return widget.cycle_focus(reverse=reverse)


def active_approval_widget(host: VeraTerminalApp) -> ApprovalBlockWidget | None:
    if host.controller.pending_approval_id is None:
        return None
    try:
        return next(
            item for item in reversed(list(host.query(ApprovalBlockWidget))) if not item._locked
        )
    except StopIteration:
        return None
