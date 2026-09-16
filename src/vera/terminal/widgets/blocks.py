"""Timeline block widgets for Textual rendering."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Collapsible, Static

from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock, format_block_clock
from vera.presentation.timeline_time import block_occurred_at
from vera.terminal.widgets.composer import COMPOSER_PROMPT, select_composer_prompt

_SELECTABLE_OPEN_KINDS = {
    BlockKind.USER,
    BlockKind.ASSISTANT,
    BlockKind.ERROR,
    BlockKind.STATUS,
    BlockKind.DIFF,
}


class TimelineBlockWidget(Vertical):
    """One DOM node per TimelineBlock."""

    DEFAULT_CSS = """
    TimelineBlockWidget {
        height: auto;
        margin: 0 2 1 2;
    }
    TimelineBlockWidget .block-title {
        padding: 0 1;
        height: auto;
    }
    TimelineBlockWidget .block-body {
        padding: 0 1;
        height: auto;
        color: $text !important;
    }
    TimelineBlockWidget .user-heading {
        height: 1;
        width: 100%;
    }
    TimelineBlockWidget .user-heading .block-title {
        width: 1fr;
        height: 1;
    }
    TimelineBlockWidget .block-time {
        width: auto;
        height: 1;
        color: $text-muted;
        text-align: right;
        padding: 0 1 0 0;
    }
    """

    def __init__(self, block: TimelineBlock) -> None:
        super().__init__(id=self._dom_id(block.block_id))
        self.block = block
        self._body = Static("", classes="block-body")
        self._title = Static(self._title_text(block), classes="block-title")
        self._time = Static(format_block_clock(block_occurred_at(block)), classes="block-time")
        self._collapsible: Collapsible | None = None
        self._markdown_render_key: tuple[str, int] | None = None

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
        if block.kind is BlockKind.USER:
            return UserBlockWidget(block)
        if block.kind is BlockKind.APPROVAL:
            from vera.terminal.widgets.approval import ApprovalBlockWidget

            return ApprovalBlockWidget(block, approval_id=approval_id or block.ref_id or "unknown")
        return cls(block)

    @property
    def collapsed(self) -> bool:
        return not self.block.expanded

    def compose(self) -> ComposeResult:
        if self.block.kind is BlockKind.USER:
            yield Horizontal(self._title, self._time, classes="user-heading")
            yield self._body
            return
        if self.block.kind in _SELECTABLE_OPEN_KINDS:
            # CollapsibleTitle sets ALLOW_SELECT=False and swallows clicks.
            # Conversation answers must stay a selectable Static body.
            yield self._title
            yield self._body
            return
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

    def on_resize(self) -> None:
        if self.block.kind in {BlockKind.ASSISTANT, BlockKind.DIFF} and self.block.body:
            self._render_body()

    def apply_block(self, block: TimelineBlock) -> None:
        self.block = block
        self._title.update(self._title_text(block))
        self._time.update(format_block_clock(block_occurred_at(block)))
        if self._collapsible is not None:
            self._collapsible.title = self._title_text(block)
            self._collapsible.collapsed = not block.expanded
        else:
            self._body.display = block.expanded
        self._render_body()

    def toggle_expanded(self) -> None:
        policy = DisclosurePolicy()
        self.block = policy.with_manual_toggle(self.block, not self.block.expanded)
        if self._collapsible is not None:
            self._collapsible.collapsed = not self.block.expanded
        else:
            self._body.display = self.block.expanded

    def _render_body(self) -> None:
        body = self.block.body
        if not self.block.expanded and self.block.kind in {BlockKind.TOOL, BlockKind.LOG}:
            # Keep text stored but avoid heavy render while collapsed.
            preview = body if len(body) <= 120 else body[:117] + "..."
            self._body.update(escape(preview) if preview else "")
            return
        if self.block.kind is BlockKind.ASSISTANT:
            width = self.size.width or 80
            key = (body, width)
            if self._markdown_render_key != key:
                self._markdown_render_key = key
                self._body.update(_assistant_markdown(body, width=width))
            return
        self._body.update(escape(body) if body else "")

    @staticmethod
    def _title_text(block: TimelineBlock) -> str:
        if block.kind is BlockKind.USER:
            return block.title
        marker = "▼" if block.expanded else "▸"
        suffix = " · incomplete" if block.incomplete else ""
        return f"{marker} {block.title}{suffix}"


class UserBlockWidget(TimelineBlockWidget):
    """User prompt as a filled bar: chevron, body, clock. No outline."""

    DEFAULT_CSS = """
    UserBlockWidget {
        width: 1fr;
        height: auto;
        min-height: 3;
        margin: 1 2;
        padding: 1 1;
        background: $secondary;
        border: none;
        color: $text !important;
    }
    UserBlockWidget .user-heading {
        height: auto;
        min-height: 1;
        width: 100%;
        content-align: left middle;
    }
    UserBlockWidget .user-prompt {
        width: 2;
        height: 1;
        color: $text-muted;
        padding: 0;
        content-align: left middle;
    }
    UserBlockWidget .block-body {
        width: 1fr;
        height: auto;
        padding: 0;
        color: $text !important;
        content-align: left middle;
    }
    UserBlockWidget .block-time {
        width: auto;
        height: 1;
        color: $text-muted;
        text-align: right;
        padding: 0 0 0 1;
        content-align: right middle;
    }
    """

    def __init__(self, block: TimelineBlock) -> None:
        super().__init__(block)
        self._title = Static(COMPOSER_PROMPT, classes="user-prompt")

    def compose(self) -> ComposeResult:
        yield Horizontal(self._title, self._body, self._time, classes="user-heading")

    def apply_block(self, block: TimelineBlock) -> None:
        self.block = block
        self._time.update(format_block_clock(block_occurred_at(block)))
        self._sync_prompt_glyph()
        self._render_body()

    def on_mount(self) -> None:
        super().on_mount()
        self._sync_prompt_glyph()

    def _sync_prompt_glyph(self) -> None:
        unicode = True
        app = self.app
        if hasattr(app, "_unicode"):
            unicode = bool(app._unicode())
        self._title.update(select_composer_prompt(unicode=unicode))


def _assistant_markdown(body: str, *, width: int = 80) -> Text:
    """Render Markdown to Rich Text so Textual can drag-select it.

    `Static.update(Markdown)` becomes a RichVisual. Widget.get_selection() only
    extracts Text/Content, so the answer would paint but never highlight or copy.
    """
    if not body:
        return Text("")
    try:
        markdown = Markdown(body, code_theme="ansi_dark", hyperlinks=False)
        console = Console(
            width=max(width, 8),
            force_terminal=True,
            color_system="standard",
            highlight=False,
        )
        rendered = Text()
        for segment in console.render(markdown, console.options):
            if segment.text:
                rendered.append(segment.text, style=segment.style)
        rendered.stylize_before("#c8cdd3")
        return rendered
    except Exception:
        return Text(body)


def _diff_text(body: str, *, width: int = 80) -> Text:
    """Render a unified diff to Rich Text so Textual can drag-select it.

    `Static.update(Syntax)` becomes a RichVisual; get_selection() only extracts
    Text/Content, so the Diff would paint but never highlight or copy.
    """
    if not body:
        return Text("")
    try:
        syntax = Syntax(body, "diff", theme="ansi_dark", word_wrap=True)
        console = Console(
            width=max(width, 8),
            force_terminal=True,
            color_system="standard",
            highlight=False,
        )
        rendered = Text()
        for segment in console.render(syntax, console.options):
            if segment.text:
                rendered.append(segment.text, style=segment.style)
        return rendered
    except Exception:
        return Text(body)


class DiffBlockWidget(TimelineBlockWidget):
    def _render_body(self) -> None:
        body = self.block.body or ""
        if not body:
            self._body.update("")
            return
        self._body.update(_diff_text(body, width=self.size.width or 80))


class EventGroupWidget(Vertical):
    """Nest adjacent same-kind blocks under one heading; each Event stays a child."""

    DEFAULT_CSS = """
    EventGroupWidget {
        height: auto;
        margin: 0 2 1 2;
        padding: 0 1;
    }
    EventGroupWidget TimelineBlockWidget {
        margin: 0;
    }
    EventGroupWidget Collapsible {
        margin: 0;
        padding-bottom: 0;
        padding-left: 0;
        border-top: none;
        background: transparent;
    }
    EventGroupWidget Collapsible Contents {
        padding: 0 0 0 1;
    }
    """

    def __init__(self, kind: BlockKind) -> None:
        super().__init__(classes=f"event-group event-group-{kind.value}")
        self.kind = kind
        self._items: list[TimelineBlockWidget] = []
        self._collapsible: Collapsible | None = None

    def compose(self) -> ComposeResult:
        self._collapsible = Collapsible(
            *self._items,
            title=self.group_title(),
            collapsed=not self.should_expand(),
        )
        yield self._collapsible

    def add_item(self, widget: TimelineBlockWidget) -> None:
        self._items.append(widget)
        if self._collapsible is not None and widget.parent is None:
            self._collapsible.mount(widget)
        self.refresh_heading()

    def refresh_heading(self) -> None:
        if self._collapsible is None:
            return
        self._collapsible.title = self.group_title()
        if self.should_expand():
            self._collapsible.collapsed = False

    def group_title(self) -> str:
        count = len(self._items)
        failed = sum(1 for item in self._items if item.block.status is BlockStatus.FAILED)
        if self.kind is BlockKind.TOOL:
            title = f"工具 · {count} 次"
        elif self.kind is BlockKind.LOG:
            title = f"日志 · {count} 条"
        else:
            title = f"状态 · {count} 项"
        if failed:
            title += f" · {failed} 失败"
        return title

    def should_expand(self) -> bool:
        if self.kind is BlockKind.STATUS:
            return True
        return any(item.block.status is BlockStatus.FAILED for item in self._items)

    def __contains__(self, block_id: object) -> bool:
        return any(item.block.block_id == block_id for item in self._items)
