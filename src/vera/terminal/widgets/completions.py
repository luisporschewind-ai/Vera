"""Slash-command and @path completion popup helpers."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from vera.session.command_catalog import CommandCatalog, CommandDescriptor
from vera.session.controller import SessionSnapshot
from vera.session.path_mentions import PathMention, suggest_path_mentions


class CompletionList(Static):
    """Simple completion list rendered above the composer."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self.catalog = CommandCatalog()
        self.display = False

    def hide(self) -> None:
        self.display = False
        self.update("")

    def update_for_prefix(
        self, prefix: str, snapshot: SessionSnapshot
    ) -> tuple[CommandDescriptor, ...]:
        if not prefix.startswith("/"):
            self.hide()
            return ()
        items = self.catalog.list(prefix, snapshot)
        if not items:
            self.hide()
            return ()
        self.display = True
        lines = [f"{item.name}  {item.description}" for item in items[:8]]
        self.update("\n".join(lines))
        return items

    def update_for_path(
        self,
        prefix: str,
        workspace: Path,
        *,
        state_dir: Path | None = None,
    ) -> tuple[PathMention, ...]:
        items = suggest_path_mentions(workspace, prefix, state_dir=state_dir)
        if not items:
            self.hide()
            return ()
        self.display = True
        lines = [f"@{item.display}  {item.kind}" for item in items[:8]]
        self.update("\n".join(lines))
        return items
