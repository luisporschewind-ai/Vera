"""Bottom prompt composer shell."""

from __future__ import annotations

from textual.widgets import TextArea


class PromptComposer(TextArea):
    """Fixed bottom input; multi-line and submit land in task 0013."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.show_line_numbers = False
