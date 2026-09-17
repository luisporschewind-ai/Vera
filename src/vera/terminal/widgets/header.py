"""Header strip for Vera wordmark and workspace chrome."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from vera.session.models import SessionStatus
from vera.terminal.brand import BrandMark, select_brand_mark
from vera.terminal.widgets.welcome import brand_header_text


class VeraHeader(Vertical):
    """Top brand strip. Activity lives on the work rail, not here."""

    DEFAULT_CSS = """
    VeraHeader {
        width: 100%;
        height: auto;
        dock: top;
        background: $boost;
        padding: 0 2;
    }
    VeraHeader #header-wordmark {
        width: 100%;
        height: auto;
        color: $accent;
        text-style: bold;
        padding: 0;
        background: transparent;
    }
    VeraHeader #header-meta {
        width: 100%;
        height: auto;
        color: $text-muted;
        padding: 0;
        background: transparent;
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
        self._mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        yield Static("VERA", id="header-wordmark")
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
        self._mark = select_brand_mark(
            columns=columns,
            rows=rows,
            unicode=unicode,
            no_color=False,
        )
        self._render_brand()

    def set_session_status(self, status: SessionStatus) -> None:
        self._status = status
        self._workspace_label = str(status.workspace)
        self._render_brand()

    def current_mark(self) -> BrandMark:
        return self._mark

    def visible_text(self) -> str:
        try:
            word = str(self.query_one("#header-wordmark", Static).render())
            meta = self.query_one("#header-meta", Static)
        except Exception:
            return "VERA"
        if meta.display is False:
            return word
        second = str(meta.render())
        if not second:
            return word
        return f"{word}\n{second}"

    def _render_brand(self) -> None:
        try:
            wordmark = self.query_one("#header-wordmark", Static)
            meta = self.query_one("#header-meta", Static)
        except Exception:
            return
        if self._status is None:
            wordmark.update(self._mark.lines[0] if self._mark.lines else "VERA")
            meta.display = False
            return
        text = brand_header_text(
            self._mark,
            self._status,
            columns=max(self._columns, 4),
            rows=max(self._rows, 1),
        )
        lines = text.splitlines()
        wordmark.update(lines[0] if lines else "VERA")
        if len(lines) > 1:
            meta.update(lines[1])
            meta.display = True
        else:
            meta.update("")
            meta.display = False
