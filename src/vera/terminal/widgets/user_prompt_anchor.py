"""Sticky mirror of the last user message that left the timeline viewport.

This is a display-only copy. It does not create Events, enter copy-all, or
change projector order.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from vera.presentation.timeline import TimelineBlock, format_block_clock
from vera.presentation.timeline_time import block_occurred_at
from vera.terminal.widgets.composer import COMPOSER_PROMPT, select_composer_prompt

AnchorMode = str


class UserPromptAnchor(Horizontal):
    """Filled overlay bar for the last scrolled-off user message."""

    can_focus = False
    DEFAULT_CSS = """
    UserPromptAnchor {
        width: auto;
        height: 3;
        display: none;
        background: $user-surface;
        border: none;
        margin: 0 2 0 2;
        padding: 1 1;
    }
    UserPromptAnchor #user-sticky-prompt {
        width: 2;
        height: 1;
        color: $text-muted;
        padding: 0;
        content-align: left middle;
    }
    UserPromptAnchor #user-sticky-body {
        width: 1fr;
        height: 1;
        overflow: hidden;
        color: $text;
        content-align: left middle;
    }
    UserPromptAnchor #user-sticky-time {
        width: auto;
        height: 1;
        color: $text-muted;
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
        self._mode: AnchorMode = "full"
        self._block: TimelineBlock | None = None

    def compose(self) -> ComposeResult:
        yield self._prompt
        yield self._body
        yield self._time

    def set_prompt(self, glyph: str) -> None:
        self._prompt.update(glyph)

    def apply_geometry(self, *, columns: int, rows: int, unicode: bool = True) -> None:
        self.set_prompt(select_composer_prompt(unicode=unicode))
        inset = 4
        if columns > inset:
            self.styles.width = columns - inset
        if columns < 60 or rows < 16:
            self._mode = "hidden"
        elif columns < 80 or rows < 24:
            self._mode = "compact"
        else:
            self._mode = "full"
        self._apply_mode()

    def show_block(self, block: TimelineBlock) -> None:
        self._block = block
        self.body_text = block.body.replace("\n", " ").strip()
        self.clock_text = format_block_clock(block_occurred_at(block))
        self._body.update(self.body_text)
        self._time.update(self.clock_text)
        self._apply_mode()

    def hide_message(self) -> None:
        self._block = None
        self.body_text = ""
        self.clock_text = ""
        self._body.update("")
        self._time.update("")
        self.display = False

    def _apply_mode(self) -> None:
        if self._mode == "hidden" or self._block is None:
            self.display = False
            return
        if self._mode == "compact":
            self.styles.height = 1
            self.styles.padding = (0, 1, 0, 1)
        else:
            self.styles.height = 3
            self.styles.padding = (1, 1, 1, 1)
        self.display = True
