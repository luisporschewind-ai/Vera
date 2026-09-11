"""Bottom status line for activity and hints."""

from __future__ import annotations

from textual.widgets import Static


class VeraStatusLine(Static):
    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("就绪 · Esc/Ctrl-C 取消 · /help", id=id)

    def set_status(self, text: str) -> None:
        self.update(text)
