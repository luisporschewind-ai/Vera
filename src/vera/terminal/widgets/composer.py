"""Bottom prompt composer with multiline submit semantics."""

from __future__ import annotations

import re

from textual._cells import cell_len
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Paste
from textual.message import Message
from textual.widgets import Static, TextArea

from vera.session.history import PromptHistory
from vera.terminal.widgets.completions import CompletionAccept, CompletionList

COMPOSER_PROMPT_ASCII = ">"
COMPOSER_PROMPT_UNICODE = "›"
COMPOSER_PROMPT = COMPOSER_PROMPT_ASCII


def select_composer_prompt(*, unicode: bool) -> str:
    return COMPOSER_PROMPT_UNICODE if unicode else COMPOSER_PROMPT_ASCII


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


class ComposerBar(Horizontal):
    """Round-bordered prompt row: a shell-style glyph plus the editor."""

    DEFAULT_CSS = """
    ComposerBar {
        width: 100%;
        min-height: 3;
        margin: 0 2 1 2;
        background: transparent;
        border: round $accent;
        padding: 0 1;
    }
    ComposerBar #composer-prompt {
        width: 2;
        height: 1;
        color: $accent;
        padding: 0;
        background: transparent;
        content-align: left top;
    }
    ComposerBar PromptComposer {
        width: 1fr;
        height: auto;
        min-height: 1;
        margin: 0;
        padding: 0;
        border: none !important;
        background: transparent !important;
        scrollbar-size: 0 0;
    }
    ComposerBar PromptComposer .text-area--cursor-line {
        background: transparent;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(COMPOSER_PROMPT, id="composer-prompt")
        yield PromptComposer(id="composer")

    def set_prompt_glyph(self, glyph: str) -> None:
        self.query_one("#composer-prompt", Static).update(glyph)


class PromptComposer(TextArea):
    """Fixed bottom input; Enter submits, Alt+Enter inserts a newline."""

    DEFAULT_CSS = """
    PromptComposer {
        scrollbar-size: 0 0;
        border: none;
        background: transparent !important;
    }
    """

    BINDINGS = [
        ("ctrl+home", "cursor_line_start", "Home"),
        ("ctrl+end", "cursor_line_end", "End"),
        ("ctrl+r", "search_history", "Search"),
    ]
    _NEWLINE_KEYS = frozenset({"alt+enter", "ctrl+j"})
    _MIN_CONTENT_LINES = 1
    _MAX_CONTENT_LINES = 5

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id, compact=True, highlight_cursor_line=False)
        self.show_line_numbers = False
        self.prompt_history = PromptHistory()
        self._search_query = ""
        self._search_matches: tuple[str, ...] = ()
        self._search_index = 0
        self._syncing_layout = False

    def clear_input(self) -> None:
        self.load_text("")
        self.sync_multiline_layout()

    def restore_draft(self, text: str) -> None:
        self.load_text(text)
        self.move_cursor_to_end()
        self.sync_multiline_layout()

    def move_cursor_to_end(self) -> None:
        lines = self.text.split("\n")
        row = max(len(lines) - 1, 0)
        self.cursor_location = (row, len(lines[row]))

    def on_mount(self) -> None:
        self.sync_multiline_layout()

    def on_resize(self, event: object | None = None) -> None:
        self.sync_multiline_layout()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area is self:
            self.call_after_refresh(self.sync_multiline_layout)

    def insert_newline(self) -> None:
        self.insert("\n")
        self.call_after_refresh(self.sync_multiline_layout)

    def _content_line_count(self) -> int:
        width = self.wrap_width
        if width < 8:
            width = max(int(self.size.width) - 1, 0)
        if width < 8:
            return max(self.text.count("\n") + 1, 1)
        total = 0
        for line in self.text.split("\n"):
            cells = max(cell_len(line), 1)
            total += max((cells + width - 1) // width, 1)
        return max(total, 1)

    def sync_multiline_layout(self) -> None:
        if self._syncing_layout:
            return
        self._syncing_layout = True
        try:
            self._apply_multiline_layout()
        finally:
            self._syncing_layout = False

    def _apply_multiline_layout(self) -> None:
        lines = self._content_line_count()
        content = min(max(lines, self._MIN_CONTENT_LINES), self._MAX_CONTENT_LINES)
        overflow = "auto" if lines > self._MAX_CONTENT_LINES else "hidden"
        self.styles.height = content
        self.styles.min_height = content
        self.styles.overflow_y = overflow
        parent = self.parent
        if parent is not None:
            bar_height = content + 2
            parent.styles.min_height = bar_height
            parent.styles.height = bar_height
        if not self.is_attached:
            return
        try:
            completions = self.app.query_one("#completions")
        except Exception:
            return
        completions.styles.margin = (0, 2, content + 4, 2)

    def submit(self) -> None:
        self.submit_text(self.text)

    def submit_text(self, text: str) -> None:
        cleaned = sanitize_composer_text(text).rstrip()
        if not cleaned.strip():
            return
        completions = self._slash_completions()
        if completions is not None:
            completions.hide()
        self.prompt_history.record(cleaned)
        self.clear_input()
        self._search_matches = ()
        self.post_message(PromptSubmitted(cleaned))

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
        if event.key in {"up", "down"} and self._move_slash_completion(
            1 if event.key == "down" else -1
        ):
            self.cursor_location = (0, len(self.text))
            event.prevent_default()
            event.stop()
            return
        if self._should_insert_newline(event):
            event.prevent_default()
            event.stop()
            self.insert_newline()
            return
        if self._slash_popup_visible() and event.character and event.character.isprintable():
            self.cursor_location = (0, len(self.text))
        if self._should_submit(event):
            event.prevent_default()
            event.stop()
            accepted = self._accepted_completion()
            if accepted is not None:
                if accepted.submit:
                    self.submit_text(accepted.text)
                else:
                    self.load_text(accepted.text)
                    self.cursor_location = (0, len(accepted.text))
                    completions = self._slash_completions()
                    if completions is not None and completions._mode == "path":
                        completions.hide()
                return
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

    def _slash_completions(self) -> CompletionList | None:
        try:
            return self.app.query_one(CompletionList)
        except Exception:
            return None

    def _move_slash_completion(self, delta: int) -> bool:
        completions = self._slash_completions()
        return bool(completions is not None and completions.navigate(delta))

    def _slash_popup_visible(self) -> bool:
        completions = self._slash_completions()
        return bool(completions is not None and completions.display)

    def _accepted_completion(self) -> CompletionAccept | None:
        completions = self._slash_completions()
        if completions is None:
            return None
        return completions.accept(self.text)

    @classmethod
    def _key_names(cls, event: object) -> set[str]:
        key = str(getattr(event, "key", ""))
        aliases = getattr(event, "aliases", ())
        return {key, *aliases}

    @classmethod
    def _should_insert_newline(cls, event: object) -> bool:
        return bool(cls._key_names(event) & cls._NEWLINE_KEYS)

    @classmethod
    def _should_submit(cls, event: object) -> bool:
        names = cls._key_names(event)
        if names & cls._NEWLINE_KEYS:
            return False
        return any(name == "enter" or name.endswith("+enter") for name in names)

    def _can_browse_history(self) -> bool:
        if not self.text.strip():
            return True
        location = getattr(self, "cursor_location", (0, 0))
        return location == (0, 0)
