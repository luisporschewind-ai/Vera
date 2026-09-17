"""Approval decision widget for the terminal timeline."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button

from vera.presentation.timeline import TimelineBlock
from vera.terminal.widgets.blocks import TimelineBlockWidget

_BUTTON_DECISIONS = (
    ("approval-cancel", "cancel"),
    ("approval-reject", "reject"),
    ("approval-approve", "approve"),
)


class ApprovalSelected(Message):
    def __init__(self, approval_id: str, decision: str) -> None:
        super().__init__()
        self.approval_id = approval_id
        self.decision = decision


class ApprovalBlockWidget(TimelineBlockWidget):
    """Approval card with Cancel as the default focused action."""

    can_focus = False
    DEFAULT_CSS = """
    ApprovalBlockWidget {
        height: auto;
        margin: 1 2;
        padding: 0;
    }
    ApprovalBlockWidget .block-title {
        padding: 0 1;
        height: auto;
    }
    ApprovalBlockWidget .block-body {
        padding: 0 1;
        height: auto;
    }
    ApprovalBlockWidget .approval-actions {
        height: auto;
        min-height: 1;
        padding: 0 1;
        margin: 0;
        width: 100%;
    }
    ApprovalBlockWidget Button {
        min-width: 8;
        width: auto;
        height: 1;
        min-height: 1;
        max-height: 1;
        padding: 0 1;
        margin: 0 1 0 0;
        border: none !important;
        border-top: none !important;
        border-bottom: none !important;
        background: $boost;
    }
    ApprovalBlockWidget Button.-primary {
        background: $accent;
        color: $text;
        border: none !important;
        border-top: none !important;
        border-bottom: none !important;
    }
    """

    def __init__(self, block: TimelineBlock, *, approval_id: str) -> None:
        super().__init__(block)
        self.approval_id = approval_id
        self.focused_decision = "cancel"
        self._locked = False
        self._cancel = Button("Cancel", id="approval-cancel", variant="primary")
        self._reject = Button("Reject", id="approval-reject")
        self._approve = Button("Approve", id="approval-approve")
        self.can_focus = False

    def compose(self) -> ComposeResult:
        yield self._title
        yield self._body
        yield Horizontal(self._cancel, self._reject, self._approve, classes="approval-actions")

    def on_mount(self) -> None:
        super().on_mount()
        self.focus_default_action()

    def on_descendant_focus(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.widget in {self._cancel, self._reject, self._approve}:
            self._sync_focus_style()

    def focus_default_action(self) -> None:
        if self._locked:
            return
        self._cancel.focus()
        self._sync_focus_style()

    def cycle_focus(self, *, reverse: bool = False) -> bool:
        if self._locked:
            return False
        buttons = self._decision_buttons()
        focused = getattr(self.app, "focused", None)
        try:
            index = buttons.index(focused)
        except ValueError:
            self.focus_default_action()
            return True
        delta = -1 if reverse else 1
        buttons[(index + delta) % len(buttons)].focus()
        self._sync_focus_style()
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._locked:
            return
        mapping = dict(_BUTTON_DECISIONS)
        decision = mapping.get(event.button.id or "")
        if decision is None:
            return
        self.focused_decision = decision
        self._locked = True
        for button in self._decision_buttons():
            button.disabled = True
        self.post_message(ApprovalSelected(self.approval_id, decision))

    def lock_actions(self) -> None:
        self._locked = True
        for button in self._decision_buttons():
            button.disabled = True

    def mark_expired(self) -> None:
        self.lock_actions()
        self.block = self.block.model_copy(
            update={"title": "审批已过期", "status": self.block.status}
        )

    def _decision_buttons(self) -> tuple[Button, Button, Button]:
        return (self._cancel, self._reject, self._approve)

    def _sync_focus_style(self) -> None:
        focused = getattr(self.app, "focused", None)
        for button, decision in zip(
            self._decision_buttons(), ("cancel", "reject", "approve"), strict=True
        ):
            if button is focused:
                button.variant = "primary"
                self.focused_decision = decision
            else:
                button.variant = "default"
