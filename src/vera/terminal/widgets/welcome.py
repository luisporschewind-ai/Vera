"""Startup chrome: identifier plus workspace/session/permission facts."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from vera import __version__
from vera.session.models import SessionStatus
from vera.terminal.brand import BrandMark
from vera.terminal.display import clip_display, display_width, pad_display


class VeraWelcome(Static):
    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self.display = False
        self._mark: BrandMark | None = None
        self._status: SessionStatus | None = None
        self._columns = 80

    def set_content(self, mark: BrandMark, status: SessionStatus, *, columns: int) -> None:
        self._mark = mark
        self._status = status
        self._columns = columns
        self.display = False
        self.update("")


def format_workspace_path(path: Path) -> str:
    try:
        home = Path.home().resolve()
        resolved = path.expanduser().resolve()
        relative = resolved.relative_to(home)
        as_posix = relative.as_posix()
        return "~" if as_posix in {"", "."} else f"~/{as_posix}"
    except Exception:
        return str(path)


def header_fact_lines(status: SessionStatus) -> tuple[str, str, str]:
    path = format_workspace_path(status.workspace)
    return (
        f"Vera  {__version__}",
        path,
        f"{status.model_name}  推理 {status.reasoning.display_label()}",
    )


def brand_header_text(
    mark: BrandMark,
    status: SessionStatus,
    *,
    columns: int,
    rows: int = 24,
    expanded: bool = True,
) -> str:
    del rows
    path = format_workspace_path(status.workspace)
    if not expanded:
        word = mark.lines[0] if mark.lines else "VERA"
        return clip_display(f"{word}  {path}", columns)
    facts = header_fact_lines(status)
    logo = mark.lines
    if len(logo) < 3:
        logo = (*logo, *("", "", ""))[:3]
    width = max((display_width(line) for line in logo), default=0)
    lines = [
        clip_display(f"{pad_display(logo[index], width)}  {facts[index]}", columns)
        for index in range(3)
    ]
    return "\n".join(lines)
