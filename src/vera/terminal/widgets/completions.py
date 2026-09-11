"""Slash-command completion popup helpers."""

from __future__ import annotations

from textual.widgets import Static

from vera.session.command_catalog import CommandCatalog, CommandDescriptor
from vera.session.controller import SessionSnapshot


class CompletionList(Static):
    """Simple completion list rendered above the composer."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self.catalog = CommandCatalog()
        self.display = False

    def update_for_prefix(
        self, prefix: str, snapshot: SessionSnapshot
    ) -> tuple[CommandDescriptor, ...]:
        if not prefix.startswith("/"):
            self.display = False
            self.update("")
            return ()
        items = self.catalog.list(prefix, snapshot)
        if not items:
            self.display = False
            self.update("")
            return ()
        self.display = True
        lines = [f"{item.name}  {item.description}" for item in items[:8]]
        self.update("\n".join(lines))
        return items
