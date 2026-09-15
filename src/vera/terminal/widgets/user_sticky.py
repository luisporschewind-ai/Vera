"""Sticky copy of the user message that just left the timeline viewport."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from vera.presentation.timeline import TimelineBlock, format_block_clock
from vera.terminal.widgets.composer import COMPOSER_PROMPT


class UserStickyBar(Horizontal):
    """Filled overlay bar for the last scrolled-off user message."""

    can_focus = False
    DEFAULT_CSS = """
    UserStickyBar {
        layer: overlay;
        dock: top;
        margin-top: 1;
        margin-left: 2;
        margin-right: 2;
        width: 100%;
        height: 3;
        display: none;
        background: $secondary;
        border: none;
        padding: 1 1;
    }
    UserStickyBar #user-sticky-prompt {
        width: 2;
        height: 1;
        color: #c5d0dc;
        padding: 0;
        content-align: left middle;
    }
    UserStickyBar #user-sticky-body {
        width: 1fr;
        height: 1;
        overflow: hidden;
        color: #ffffff;
        content-align: left middle;
    }
    UserStickyBar #user-sticky-time {
        width: auto;
        height: 1;
        color: #6e7782 !important;
        text-align: right;
        padding: 0 0 0 1;
        content-align: right middle;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._prompt = Static(COMPOSER_PROMPT, id="user-sticky-prompt")
        self._body = Static("", id="user-sticky-body")
        self._time = Static("", id="user-sticky-time")
        self.body_text = ""
        self.clock_text = ""

    def compose(self) -> ComposeResult:
        yield self._prompt
        yield self._body
        yield self._time

    def show_block(self, block: TimelineBlock) -> None:
        self.body_text = block.body.replace("\n", " ").strip()
        self.clock_text = format_block_clock(block.created_at)
        self._body.update(self.body_text)
        self._time.update(self.clock_text)
        self.display = True

    def hide_message(self) -> None:
        self.body_text = ""
        self.clock_text = ""
        self._body.update("")
        self._time.update("")
        self.display = False
