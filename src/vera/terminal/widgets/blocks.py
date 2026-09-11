"""Timeline block widgets for Textual rendering."""

from __future__ import annotations

from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Collapsible, Static

from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.timeline import BlockKind, TimelineBlock


class TimelineBlockWidget(Vertical):
    """One DOM node per TimelineBlock."""

    DEFAULT_CSS = """
    TimelineBlockWidget {
        height: auto;
        margin: 0 0 1 0;
    }
    TimelineBlockWidget .block-body {
        padding: 0 1;
    }
    """

    def __init__(self, block: TimelineBlock) -> None:
        super().__init__(id=self._dom_id(block.block_id))
        self.block = block
        self._body = Static("", classes="block-body")
        self._title = Static(self._title_text(block), classes="block-title")
        self._collapsible: Collapsible | None = None

    @staticmethod
    def _dom_id(block_id: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in block_id)
        return f"block-{safe}"

    @classmethod
    def from_model(
        cls, block: TimelineBlock, *, approval_id: str | None = None
    ) -> TimelineBlockWidget:
        if block.kind is BlockKind.DIFF:
            return DiffBlockWidget(block)
        if block.kind is BlockKind.APPROVAL:
            from vera.terminal.widgets.approval import ApprovalBlockWidget

            return ApprovalBlockWidget(block, approval_id=approval_id or block.ref_id or "unknown")
        return cls(block)

    @property
    def collapsed(self) -> bool:
        return not self.block.expanded

    def compose(self) -> ComposeResult:
        collapsed = not self.block.expanded
        self._collapsible = Collapsible(
            self._body,
            title=self._title_text(self.block),
            collapsed=collapsed,
            id=f"{self.id}-collapse",
        )
        yield self._collapsible

    def on_mount(self) -> None:
        self._render_body()

    def apply_block(self, block: TimelineBlock) -> None:
        self.block = block
        if self._collapsible is not None:
            self._collapsible.title = self._title_text(block)
            self._collapsible.collapsed = not block.expanded
        self._render_body()

    def toggle_expanded(self) -> None:
        policy = DisclosurePolicy()
        self.block = policy.with_manual_toggle(self.block, not self.block.expanded)
        if self._collapsible is not None:
            self._collapsible.collapsed = not self.block.expanded

    def _render_body(self) -> None:
        body = self.block.body
        if not self.block.expanded and self.block.kind in {BlockKind.TOOL, BlockKind.LOG}:
            # Keep text stored but avoid heavy render while collapsed.
            preview = body if len(body) <= 120 else body[:117] + "..."
            self._body.update(escape(preview) if preview else "")
            return
        if self.block.kind is BlockKind.ASSISTANT:
            self._body.update(Text(body))
            return
        self._body.update(escape(body) if body else "")

    @staticmethod
    def _title_text(block: TimelineBlock) -> str:
        marker = "▼" if block.expanded else "▸"
        suffix = " · incomplete" if block.incomplete else ""
        return f"{marker} {block.title}{suffix}"


class DiffBlockWidget(TimelineBlockWidget):
    def _render_body(self) -> None:
        body = self.block.body or ""
        if not body:
            self._body.update("")
            return
        # Treat as plain unified diff text; never interpret as Rich markup.
        try:
            self._body.update(Syntax(body, "diff", theme="ansi_dark", word_wrap=True))
        except Exception:
            self._body.update(Text(body))
