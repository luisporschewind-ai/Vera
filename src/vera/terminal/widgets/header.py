"""Header strip for Vera wordmark and workspace chrome."""

from __future__ import annotations

from math import exp

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from vera.session.models import SessionStatus
from vera.terminal.brand import BrandMark, select_brand_mark
from vera.terminal.widgets.welcome import brand_header_text, header_fact_lines

_WAVE_CREST = Style(bold=True, color="#548EA0")
_WAVE_TROUGH = Style(bold=False, color="#3D7A8C")


def logo_wave_value(*, row: int, column: int, phase: float) -> float:
    """One soft crest travels bottom-left → top-right as phase increases."""

    along = column + (2 - row) * 3.2
    center = phase * 34.0
    return exp(-(((along - center) / 5.2) ** 2))


def wave_glyph_style(value: float) -> Style:
    """A narrow highlight without terminal `dim`, which paints braille as pale blocks."""

    return _WAVE_CREST if value > 0.45 else _WAVE_TROUGH


class VeraHeader(Horizontal):
    """Top brand strip. Activity lives on the work rail, not here."""

    DEFAULT_CSS = """
    VeraHeader {
        width: 100%;
        height: auto;
        dock: top;
        background: $boost;
        padding: 0 2;
    }
    VeraHeader.-welcome {
        padding: 1 2;
    }
    VeraHeader #header-wordmark {
        width: auto;
        height: auto;
        color: $accent;
        text-style: bold;
        padding: 0;
        margin-right: 2;
        background: $boost;
    }
    VeraHeader #header-meta {
        width: 1fr;
        height: auto;
        color: $text-muted;
        padding: 0;
        background: $boost;
    }
    """

    def __init__(
        self,
        *,
        model_profile: str = "default",
        workspace_label: str = ".",
        id: str | None = None,
    ) -> None:
        self._model_profile = model_profile
        self._workspace_label = workspace_label
        self._status: SessionStatus | None = None
        self._columns = 80
        self._rows = 24
        self._unicode = True
        self._expanded = True
        self._wave_phase: float | None = None
        self._mark = select_brand_mark(
            columns=80, rows=24, unicode=True, no_color=False, expanded=True
        )
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        yield Static("", id="header-wordmark")
        yield Static("", id="header-meta")

    def set_narrow(self, narrow: bool) -> None:
        self.set_class(narrow, "-narrow")
        columns = 60 if narrow else 80
        rows = 16 if narrow else 24
        self.apply_geometry(columns=columns, rows=rows, unicode=True)

    def apply_geometry(self, *, columns: int, rows: int, unicode: bool) -> None:
        self.set_class(columns < 80, "-narrow")
        self._columns = columns
        self._rows = rows
        self._unicode = unicode
        self._sync_mark()
        self._render_brand()

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.set_class(expanded, "-welcome")
        self._sync_mark()
        self._render_brand()

    def set_wave_phase(self, phase: float | None) -> None:
        self._wave_phase = phase
        self._render_brand()

    def set_session_status(self, status: SessionStatus) -> None:
        self._status = status
        self._workspace_label = str(status.workspace)
        self._render_brand()

    def current_mark(self) -> BrandMark:
        return self._mark

    def visible_text(self) -> str:
        if self._status is None:
            return "\n".join(self._mark.lines) or "VERA"
        return brand_header_text(
            self._mark,
            self._status,
            columns=max(self._columns, 4),
            rows=max(self._rows, 1),
            expanded=self._expanded,
        )

    def _sync_mark(self) -> None:
        self._mark = select_brand_mark(
            columns=self._columns,
            rows=self._rows,
            unicode=self._unicode,
            no_color=False,
            expanded=self._expanded,
        )

    def _render_brand(self) -> None:
        try:
            wordmark = self.query_one("#header-wordmark", Static)
            meta = self.query_one("#header-meta", Static)
        except Exception:
            return
        self.set_class(self._expanded, "-welcome")
        if self._status is None:
            wordmark.update(self._logo_visual(self._mark.lines))
            meta.update("")
            meta.display = True
            return
        if not self._expanded:
            text = brand_header_text(
                self._mark,
                self._status,
                columns=max(self._columns, 4),
                expanded=False,
            )
            wordmark.update(text)
            meta.update("")
            meta.display = True
            return
        facts = header_fact_lines(self._status)
        wordmark.update(self._logo_visual(self._mark.lines))
        meta.update("\n".join(facts))
        meta.display = True

    def _logo_visual(self, lines: tuple[str, ...]) -> str | Text:
        if self._wave_phase is None:
            return "\n".join(lines)
        out = Text()
        for row, line in enumerate(lines):
            if row:
                out.append("\n")
            for index, char in enumerate(line):
                if char == " ":
                    out.append(" ")
                    continue
                value = logo_wave_value(row=row, column=index, phase=self._wave_phase)
                out.append(char, style=wave_glyph_style(value))
        return out
