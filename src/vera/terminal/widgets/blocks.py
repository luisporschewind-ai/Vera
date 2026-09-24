"""Timeline block widgets for Textual rendering."""

from __future__ import annotations

import re

from rich.cells import cell_len, chop_cells
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.style import Style
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
    TimelineBlockWidget.assistant .block-body {
        text-wrap: nowrap;
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
        if block.kind is BlockKind.ASSISTANT:
            self.add_class("assistant")
        self._body = Static("", classes="block-body")
        self._title = Static(self._title_text(block), classes="block-title")
        self._time = Static(format_block_clock(block_occurred_at(block)), classes="block-time")
        self._collapsible: Collapsible | None = None
        self._markdown_render_key: tuple[str, int, str] | None = None
        self._markdown_text: Text | None = None
        self._visible_lines: int | None = None

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

    def set_visible_lines(self, count: int | None) -> None:
        """Limit displayed answer rows without changing the authoritative block body."""
        self._visible_lines = None if count is None else max(1, count)
        if self.block.kind is BlockKind.ASSISTANT:
            self._render_body()

    @property
    def visible_line_count(self) -> int:
        return self.assistant_line_count if self._visible_lines is None else self._visible_lines

    @property
    def assistant_line_count(self) -> int:
        if self.block.kind is not BlockKind.ASSISTANT:
            return 0
        return len(self._rendered_assistant().split(allow_blank=True))

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
            rendered = self._rendered_assistant()
            if self._visible_lines is None:
                self._body.update(rendered)
            else:
                visible = Text()
                for index, line in enumerate(
                    rendered.split(allow_blank=True)[: self._visible_lines]
                ):
                    if index:
                        visible.append("\n")
                    visible.append_text(line)
                self._body.update(visible)
            return
        self._body.update(escape(body) if body else "")

    def _rendered_assistant(self) -> Text:
        key = (
            self.block.body,
            self._assistant_content_width(),
            str(getattr(self.app, "theme", "default")),
        )
        if self._markdown_render_key != key or self._markdown_text is None:
            self._markdown_render_key = key
            self._markdown_text = _assistant_markdown(key[0], width=key[1], theme=key[2])
        return self._markdown_text

    def _assistant_content_width(self) -> int:
        width = self._body.size.width or self.size.width or 80
        padding = self._body.styles.padding
        inner = int(width) - int(padding.left) - int(padding.right)
        return max(inner, 8)

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


_ASSISTANT_WRAP_TOKEN = re.compile(r"\s+|[A-Za-z0-9_.-]+/?|.", flags=re.DOTALL)
_FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})")
_TABLE_SEP_CELL = re.compile(r"^:?-{3,}:?$")
_DIFF_ADD = Style(color="#7EB89A")
_DIFF_REMOVE = Style(color="#D98989")
_DIFF_META = Style(color="#7E96A8", bold=True)
_DIFF_HUNK = Style(color="#5B9BB0")


def _assistant_wrap_offsets(plain: str, width: int) -> list[int]:
    """Break after spaces, `/`, and CJK glyphs; keep dotted filenames intact."""
    if width < 1 or not plain:
        return []
    breaks: list[int] = []
    column = 0
    for match in _ASSISTANT_WRAP_TOKEN.finditer(plain):
        token = match.group(0)
        start = match.start()
        if token.isspace():
            space_width = cell_len(token)
            if column == 0:
                column += space_width
                continue
            if column + space_width > width:
                breaks.append(start)
                column = 0
                continue
            column += space_width
            continue
        token_width = cell_len(token)
        if column + token_width <= width:
            column += token_width
            continue
        if token_width > width:
            if column and start:
                breaks.append(start)
            pieces = chop_cells(token, width=width)
            offset = start
            for index, piece in enumerate(pieces):
                if index:
                    breaks.append(offset)
                if index == len(pieces) - 1:
                    column = cell_len(piece)
                else:
                    offset += len(piece)
            continue
        if start:
            breaks.append(start)
        column = token_width
    return breaks


def _wrap_assistant_text(text: Text, width: int) -> Text:
    wrapped = Text()
    lines = text.split(allow_blank=True)
    last_index = len(lines) - 1
    for index, line in enumerate(lines):
        line.rstrip()
        parts = line.divide(_assistant_wrap_offsets(line.plain, width))
        for part_index, part in enumerate(parts):
            part.rstrip()
            if part_index:
                wrapped.append("\n")
            wrapped.append_text(part)
        if index != last_index:
            wrapped.append("\n")
    return wrapped


def _assistant_markdown(body: str, *, width: int = 80, theme: str = "default") -> Text:
    """Render Markdown to Rich Text so Textual can drag-select it.

    `Static.update(Markdown)` becomes a RichVisual. Widget.get_selection() only
    extracts Text/Content, so the answer would paint but never highlight or copy.
    Tables and fences layout at the content width; prose still uses path/CJK wrap.
    """
    if not body:
        return Text("")
    wrap_width = max(width, 8)
    rendered = Text()
    try:
        for kind, chunk in _iter_markdown_chunks(body):
            if not chunk:
                continue
            if kind in {"table", "fence"}:
                rendered.append_text(
                    _render_markdown_text(chunk, width=wrap_width, no_wrap=False, theme=theme)
                )
            else:
                prose = _render_markdown_text(
                    chunk, width=max(wrap_width * 4, 256), no_wrap=True, theme=theme
                )
                rendered.append_text(_wrap_assistant_text(prose, wrap_width))
        if not rendered.plain:
            return _wrap_assistant_text(Text(body), wrap_width)
        rendered.stylize_before(_assistant_body_color(theme))
        return rendered
    except Exception:
        return _wrap_assistant_text(Text(body), wrap_width)


def _assistant_body_color(theme: str) -> str:
    if theme == "light":
        return "#1A2B36"
    if theme == "cream":
        return "#3D3429"
    if theme == "high-contrast":
        return "#FFFFFF"
    if theme == "no-color":
        return "#E0E0E0"
    return "#c8cdd3"


def _render_markdown_text(body: str, *, width: int, no_wrap: bool, theme: str = "default") -> Text:
    code_theme = "ansi_light" if theme in {"light", "cream"} else "ansi_dark"
    markdown = Markdown(body, code_theme=code_theme, hyperlinks=False)
    console = Console(
        width=max(width, 8),
        force_terminal=True,
        color_system="standard",
        highlight=False,
    )
    rendered = Text()
    options = console.options.update(no_wrap=no_wrap, overflow="ignore")
    for segment in console.render(markdown, options):
        if segment.text:
            rendered.append(segment.text, style=segment.style)
    return rendered


def _iter_markdown_chunks(body: str) -> list[tuple[str, str]]:
    lines = body.splitlines(keepends=True)
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    index = 0

    def flush() -> None:
        if buffer:
            chunks.append(("copy", "".join(buffer)))
            buffer.clear()

    while index < len(lines):
        fence = _consume_fence(lines, index)
        if fence is not None:
            flush()
            chunk, index = fence
            chunks.append(("fence", chunk))
            continue
        table = _consume_table(lines, index)
        if table is not None:
            flush()
            chunk, index = table
            chunks.append(("table", chunk))
            continue
        buffer.append(lines[index])
        index += 1
    flush()
    return chunks


def _consume_fence(lines: list[str], start: int) -> tuple[str, int] | None:
    match = _FENCE_OPEN.match(lines[start])
    if match is None:
        return None
    marker = match.group(2)
    collected = [lines[start]]
    index = start + 1
    closing = re.compile(rf"^\s*{re.escape(marker[0] * len(marker))}\s*$")
    while index < len(lines):
        collected.append(lines[index])
        if closing.match(lines[index].rstrip("\n")):
            index += 1
            break
        index += 1
    return "".join(collected), index


def _consume_table(lines: list[str], start: int) -> tuple[str, int] | None:
    if start + 1 >= len(lines):
        return None
    if not _table_row(lines[start]) or not _table_separator(lines[start + 1]):
        return None
    collected = [lines[start], lines[start + 1]]
    index = start + 2
    while index < len(lines) and _table_row(lines[index]):
        collected.append(lines[index])
        index += 1
    return "".join(collected), index


def _table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and not _table_separator(line)


def _table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(_TABLE_SEP_CELL.fullmatch(cell) is not None for cell in cells)


def _diff_text(body: str, *, width: int = 80) -> Text:
    """Render a unified diff to Rich Text so Textual can drag-select it."""
    if not body:
        return Text("")
    wrap_width = max(width, 8)
    rendered = Text()
    for index, line in enumerate(body.splitlines()):
        if index:
            rendered.append("\n")
        style = _diff_line_style(line)
        parts = _wrap_diff_line(line, wrap_width)
        for part_index, part in enumerate(parts):
            if part_index:
                rendered.append("\n")
            rendered.append(part, style=style)
    return rendered


def _diff_line_style(line: str) -> Style | None:
    if line.startswith(("---", "+++")):
        return _DIFF_META
    if line.startswith("@@"):
        return _DIFF_HUNK
    if line.startswith("+"):
        return _DIFF_ADD
    if line.startswith("-"):
        return _DIFF_REMOVE
    return None


def _wrap_diff_line(line: str, width: int) -> list[str]:
    if cell_len(line) <= width:
        return [line]
    marker = ""
    rest = line
    if line.startswith(("+++", "---", "@@")):
        rest = line
    elif line[:1] in "+- ":
        marker = line[:1]
        rest = line[1:]
    budget = max(width - cell_len(marker), 8)
    wrapped = Text(rest)
    parts = wrapped.divide(_assistant_wrap_offsets(rest, budget))
    result: list[str] = []
    for part in parts:
        part.rstrip()
        result.append(marker + part.plain)
    return result or [line]


class DiffBlockWidget(TimelineBlockWidget):
    def _render_body(self) -> None:
        body = self.block.body or ""
        if not body:
            self._body.update("")
            return
        self._body.update(_diff_text(body, width=self._assistant_content_width()))


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
        if self._has_failure():
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
        return self.kind is BlockKind.STATUS or self._has_failure()

    def _has_failure(self) -> bool:
        return any(item.block.status is BlockStatus.FAILED for item in self._items)

    def __contains__(self, block_id: object) -> bool:
        return any(item.block.block_id == block_id for item in self._items)
