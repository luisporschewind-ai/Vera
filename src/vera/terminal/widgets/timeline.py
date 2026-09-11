"""Scrollable conversation timeline shell."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class ConversationTimeline(VerticalScroll):
    """Placeholder timeline region; cards arrive in later tasks."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._placeholder = Static("对话时间线", classes="timeline-placeholder")

    def compose(self):  # type: ignore[no-untyped-def]
        yield self._placeholder
