"""Bottom prompt composer with multiline submit semantics."""

from __future__ import annotations

from textual.message import Message
from textual.widgets import TextArea


class PromptSubmitted(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class PromptComposer(TextArea):
    """Fixed bottom input; Enter submits single-line, Ctrl+Enter submits multiline."""

    BINDINGS = [
        ("ctrl+j", "insert_newline", "Newline"),
        ("ctrl+enter", "submit_prompt", "Submit"),
    ]

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.show_line_numbers = False
        self._history: list[str] = []
        self._history_index = -1

    def clear_input(self) -> None:
        self.load_text("")

    def insert_newline(self) -> None:
        self.insert("\n")

    def submit(self) -> None:
        text = self.text.rstrip("\n")
        if not text.strip():
            return
        self._history.append(text)
        self._history_index = len(self._history)
        self.clear_input()
        self.post_message(PromptSubmitted(text))

    def action_insert_newline(self) -> None:
        self.insert_newline()

    def action_submit_prompt(self) -> None:
        self.submit()

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key == "enter":
            if "\n" in self.text:
                return
            event.prevent_default()
            event.stop()
            self.submit()
            return
        if event.key == "up" and not self.text.strip() and self._history:
            self._history_index = max(0, self._history_index - 1)
            self.load_text(self._history[self._history_index])
            event.prevent_default()
            event.stop()
