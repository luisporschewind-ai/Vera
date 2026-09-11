"""Approval decision widget for the terminal timeline."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static

from vera.presentation.timeline import TimelineBlock
from vera.terminal.widgets.blocks import TimelineBlockWidget


class ApprovalSelected(Message):
    def __init__(self, approval_id: str, decision: str) -> None:
        super().__init__()
        self.approval_id = approval_id
        self.decision = decision


class ApprovalBlockWidget(TimelineBlockWidget):
    """Approval card with Cancel as the default focused action."""

    def __init__(self, block: TimelineBlock, *, approval_id: str) -> None:
        super().__init__(block)
        self.approval_id = approval_id
        self.focused_decision = "cancel"
        self._locked = False
        self._cancel = Button("Cancel", id="approval-cancel", variant="primary")
        self._reject = Button("Reject", id="approval-reject")
        self._approve = Button("Approve", id="approval-approve")

    def compose(self) -> ComposeResult:
        yield Static(self._title_text(self.block), classes="block-title")
        yield Static(self.block.body or "等待审批", classes="block-body")
        yield Horizontal(self._cancel, self._reject, self._approve, classes="approval-actions")

    def on_mount(self) -> None:
        self._cancel.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._locked:
            return
        mapping = {
            "approval-cancel": "cancel",
            "approval-reject": "reject",
            "approval-approve": "approve",
        }
        decision = mapping.get(event.button.id or "")
        if decision is None:
            return
        self.focused_decision = decision
        self._locked = True
        for button in (self._cancel, self._reject, self._approve):
            button.disabled = True
        self.post_message(ApprovalSelected(self.approval_id, decision))

    def lock_actions(self) -> None:
        self._locked = True
        for button in (self._cancel, self._reject, self._approve):
            button.disabled = True
