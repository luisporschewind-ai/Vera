"""Slash-command and @path completion popup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape
from textual.widgets import Static

from vera.session.command_catalog import CommandCatalog, CommandDescriptor
from vera.session.controller import SessionSnapshot
from vera.session.path_mentions import PathMention, suggest_path_mentions
from vera.terminal.theme import ThemeName, matching_themes

_WINDOW = 12


@dataclass(frozen=True)
class CompletionAccept:
    text: str
    submit: bool


class CompletionList(Static):
    """Completion list above the composer; slash rows can be highlighted and accepted."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self.can_focus = False
        self.catalog = CommandCatalog()
        self.display = False
        self.last_query = ""
        self.needs_restore = False
        self.has_selection_style = False
        self._mode: str | None = None
        self._slash_items: tuple[CommandDescriptor, ...] = ()
        self._theme_items: tuple[tuple[ThemeName, str], ...] = ()
        self._path_items: tuple[PathMention, ...] = ()
        self._selected = 0

    def hide(self) -> None:
        self.display = False
        self.last_query = ""
        self.needs_restore = False
        self.has_selection_style = False
        self._mode = None
        self._slash_items = ()
        self._theme_items = ()
        self._path_items = ()
        self._selected = 0
        self.update("")

    def visible_text(self) -> str:
        content = self.content
        plain = getattr(content, "plain", None)
        if isinstance(plain, str):
            return plain
        return str(content)

    def update_for_input(self, text: str, snapshot: SessionSnapshot) -> bool:
        stripped = text.lstrip()
        query = resolve_slash_query(
            stripped,
            active=self.display and self._mode == "slash",
            catalog=self.catalog,
            snapshot=snapshot,
        )
        if query is None:
            keep = bool(self.display and self._mode == "slash" and not stripped)
            if not keep:
                self.hide()
            return keep
        self.last_query = query
        self.needs_restore = not stripped.startswith("/")
        if stripped.startswith("/"):
            parts = stripped.split()
            token = parts[0] if parts else stripped
            command = self.catalog.get(token)
            if command is not None and command.name == "/theme":
                remainder = stripped[len(token) :]
                if remainder.startswith(" ") or remainder.startswith("\t"):
                    arg = parts[1] if len(parts) > 1 else ""
                    self.update_for_themes(arg)
                    return self.display
            self.update_for_prefix(token, snapshot)
            return self.display
        self.update_for_prefix(query, snapshot)
        return self.display

    def update_for_prefix(
        self, prefix: str, snapshot: SessionSnapshot
    ) -> tuple[CommandDescriptor, ...]:
        if not prefix.startswith("/"):
            self.hide()
            return ()
        items = self.catalog.list(prefix, snapshot)
        previous = (
            self._slash_items[self._selected].name
            if self._mode == "slash" and self._slash_items
            else None
        )
        self._mode = "slash"
        self._theme_items = ()
        self._path_items = ()
        self._slash_items = items
        self._selected = 0
        if previous:
            for index, item in enumerate(items):
                if item.name == previous:
                    self._selected = index
                    break
        self._render_rows(
            [(item.name, item.description) for item in items],
            heading=f"斜杠命令 · {len(items)}",
            empty="没有匹配的命令",
        )
        return items

    def update_for_themes(self, prefix: str) -> tuple[tuple[ThemeName, str], ...]:
        items = matching_themes(prefix)
        previous = (
            self._theme_items[self._selected][0]
            if self._mode == "theme" and self._theme_items
            else None
        )
        self._mode = "theme"
        self._slash_items = ()
        self._path_items = ()
        self._theme_items = items
        self._selected = 0
        if previous:
            for index, (name, _label) in enumerate(items):
                if name == previous:
                    self._selected = index
                    break
        self._render_rows(
            list(items),
            heading=f"主题 · {len(items)}",
            empty="没有匹配的主题",
        )
        return items

    def update_for_path(
        self,
        prefix: str,
        workspace: Path,
        *,
        state_dir: Path | None = None,
    ) -> tuple[PathMention, ...]:
        items = suggest_path_mentions(workspace, prefix, state_dir=state_dir)
        self._mode = "path"
        self._slash_items = ()
        self._theme_items = ()
        self._path_items = items
        self._selected = 0
        self._render_rows(
            [(f"@{item.display}", item.kind) for item in items],
            heading=f"路径 · {len(items)}",
            empty="没有匹配的路径",
        )
        return items

    def navigate(self, delta: int) -> bool:
        rows = self._row_count()
        if not self.display or rows == 0:
            return False
        self._selected = max(0, min(rows - 1, self._selected + delta))
        if self._mode == "slash":
            self._render_rows(
                [(item.name, item.description) for item in self._slash_items],
                heading=f"斜杠命令 · {len(self._slash_items)}",
                empty="没有匹配的命令",
            )
            return True
        if self._mode == "theme":
            self._render_rows(
                list(self._theme_items),
                heading=f"主题 · {len(self._theme_items)}",
                empty="没有匹配的主题",
            )
            return True
        if self._mode == "path":
            self._render_rows(
                [(f"@{item.display}", item.kind) for item in self._path_items],
                heading=f"路径 · {len(self._path_items)}",
                empty="没有匹配的路径",
            )
            return True
        return False

    def accept(self, typed: str) -> CompletionAccept | None:
        if self._mode == "path" and self.display and self._path_items:
            mention = self._path_items[self._selected]
            return CompletionAccept(
                text=replace_path_mention(typed, mention.display),
                submit=False,
            )
        if self._mode == "theme" and self.display and self._theme_items:
            name, _label = self._theme_items[self._selected]
            return CompletionAccept(text=f"/theme {name}", submit=True)
        if self._mode != "slash" or not self.display or not self._slash_items:
            return None
        selected = self._slash_items[self._selected]
        stripped = typed.strip()
        if not stripped.startswith("/"):
            return None
        parts = stripped.split()
        token = parts[0]
        extra = parts[1:]
        if self.catalog.get(token) is not None:
            if selected.name == "/theme" and not extra:
                return CompletionAccept(text="/theme ", submit=False)
            return CompletionAccept(text=stripped, submit=True)
        if selected.name == "/theme" and not extra:
            return CompletionAccept(text="/theme ", submit=False)
        if extra:
            return CompletionAccept(text=" ".join((selected.name, *extra)), submit=True)
        return CompletionAccept(text=selected.name, submit=True)

    def accepted_slash_command(self, typed: str) -> str | None:
        accepted = self.accept(typed)
        if accepted is None or not accepted.submit:
            return None
        return accepted.text

    def _row_count(self) -> int:
        if self._mode == "slash":
            return len(self._slash_items)
        if self._mode == "theme":
            return len(self._theme_items)
        if self._mode == "path":
            return len(self._path_items)
        return 0

    def _render_rows(
        self,
        rows: list[tuple[str, str]],
        *,
        heading: str,
        empty: str,
    ) -> None:
        width = max(8, (self.size.width or 80) - 2)
        lines = [escape(heading)]
        self.has_selection_style = False
        if not rows:
            lines.append(f"  {escape(empty)}")
        else:
            start = _window_start(self._selected, len(rows), _WINDOW)
            visible = rows[start : start + _WINDOW]
            selected = self._selected_markup()
            for offset, (name, description) in enumerate(visible):
                index = start + offset
                label = _fit_row(name, description, width)
                if index == self._selected:
                    self.has_selection_style = True
                    lines.append(f"[{selected}]{escape(f'▸ {label}'.ljust(width))}[/]")
                else:
                    lines.append(f"  {escape(label)}")
            if len(rows) > _WINDOW:
                last = start + len(visible)
                lines.append(f"  {start + 1}–{last} / {len(rows)}  ↑↓")
        self.display = True
        self.update("\n".join(lines))

    def _selected_markup(self) -> str:
        theme = "default"
        try:
            theme = str(getattr(self.app, "theme", "default"))
        except Exception:
            theme = "default"
        if theme == "high-contrast":
            return "bold #000000 on #ffff00"
        if theme == "no-color":
            return "bold #000000 on #c8c8c8"
        return "bold #E8EEF6 on #2A5F9E"


def resolve_slash_query(
    text: str,
    *,
    active: bool,
    catalog: CommandCatalog,
    snapshot: SessionSnapshot,
) -> str | None:
    """Return the slash token to complete, even if IME or cursor ate the leading /."""

    stripped = text.lstrip()
    if stripped.startswith("/"):
        parts = stripped.split()
        return parts[0] if parts else stripped
    if "@" in stripped:
        return None
    slash_at = stripped.find("/")
    if slash_at >= 0 and active:
        before = stripped[:slash_at]
        fragment = stripped[slash_at:]
        token = fragment.split()[0] if fragment.split() else fragment
        if before and _is_command_fragment(before):
            inferred = token + before if token == "/" else token
            if catalog.list(inferred, snapshot):
                return inferred
        return None
    if active and stripped and _is_command_fragment(stripped):
        inferred = f"/{stripped}"
        if catalog.list(inferred, snapshot):
            return inferred
    return None


def replace_path_mention(typed: str, display: str) -> str:
    """Replace the last @fragment with a completed mention plus a trailing space."""

    mention = f"@{display} "
    index = typed.rfind("@")
    if index < 0:
        return mention
    return typed[:index] + mention


def _is_command_fragment(text: str) -> bool:
    return all(character.isalnum() or character in "-_" for character in text)


def _window_start(selected: int, total: int, window: int) -> int:
    if total <= window:
        return 0
    start = 0 if selected < window else selected - window + 1
    return min(start, total - window)


def _fit_row(name: str, description: str, width: int) -> str:
    text = f"{name}  {description}" if description else name
    limit = max(8, width - 2)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
