"""Header strip for Vera wordmark and workspace chrome."""

from __future__ import annotations

from textual.widgets import Static

from vera.session.models import SessionStatus
from vera.terminal.brand import BrandMark, select_brand_mark
from vera.terminal.widgets.welcome import brand_header_text


class VeraHeader(Static):
    """Top brand strip. Model and activity live on the footer, not here."""

    DEFAULT_CSS = """
    VeraHeader {
        width: 100%;
        height: auto;
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
        super().__init__("VERA", id=id)

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

    def _render_brand(self) -> None:
        if self._status is None:
            self.update(self._mark.lines[0] if self._mark.lines else "VERA")
            return
        self.update(
            brand_header_text(
                self._mark,
                self._status,
                columns=max(self._columns, 4),
                rows=max(self._rows, 1),
            )
        )
