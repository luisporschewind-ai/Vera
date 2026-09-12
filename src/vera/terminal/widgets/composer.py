"""Bottom prompt composer with multiline submit semantics."""

from __future__ import annotations

import re

from textual.events import Paste
from textual.message import Message
from textual.widgets import TextArea

from vera.session.history import PromptHistory

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ESC = re.compile(r"\x1b.")
_BIDI = re.compile(r"[\u202a-\u202e\u2066-\u2069]")


def sanitize_composer_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _OSC.sub("", normalized)
    normalized = _CSI.sub("", normalized)
    normalized = _ESC.sub("", normalized)
    normalized = _BIDI.sub("", normalized)
    return _CONTROL.sub("", normalized)


class PromptSubmitted(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class PromptComposer(TextArea):
    """Fixed bottom input; Enter submits single-line, Ctrl+Enter submits multiline."""

    BINDINGS = [
        ("ctrl+j", "insert_newline", "Newline"),
        ("ctrl+enter", "submit_prompt", "Submit"),
        ("ctrl+home", "cursor_line_start", "Home"),
        ("ctrl+end", "cursor_line_end", "End"),
        ("ctrl+r", "search_history", "Search"),
    ]

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.show_line_numbers = False
        self.prompt_history = PromptHistory()
        self._search_query = ""
        self._search_matches: tuple[str, ...] = ()
        self._search_index = 0

    def clear_input(self) -> None:
        self.load_text("")

    def insert_newline(self) -> None:
        self.insert("\n")

    def submit(self) -> None:
        text = sanitize_composer_text(self.text).rstrip("\n")
        if not text.strip():
            return
        self.prompt_history.record(text)
        self.clear_input()
        self._search_matches = ()
        self.post_message(PromptSubmitted(text))

    def action_insert_newline(self) -> None:
        self.insert_newline()

    def action_submit_prompt(self) -> None:
        self.submit()

    def action_search_history(self) -> None:
        query = sanitize_composer_text(self.text).strip()
        if query != self._search_query or not self._search_matches:
            self._search_query = query
            self._search_matches = self.prompt_history.search(query)
            self._search_index = 0
        elif self._search_matches:
            self._search_index = (self._search_index + 1) % len(self._search_matches)
        if not self._search_matches:
            return
        self.load_text(self._search_matches[self._search_index])

    def on_paste(self, event: Paste) -> None:
        event.prevent_default()
        event.stop()
        self.insert(sanitize_composer_text(event.text))

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key == "enter":
            if "\n" in self.text:
                return
            event.prevent_default()
            event.stop()
            self.submit()
            return
        if event.key == "up" and self._can_browse_history():
            self.load_text(self.prompt_history.up(self.text))
            event.prevent_default()
            event.stop()
            return
        if event.key == "down" and self.prompt_history.browsing():
            self.load_text(self.prompt_history.down())
            event.prevent_default()
            event.stop()

    def _can_browse_history(self) -> bool:
        if not self.text.strip():
            return True
        location = getattr(self, "cursor_location", (0, 0))
        return location == (0, 0)
