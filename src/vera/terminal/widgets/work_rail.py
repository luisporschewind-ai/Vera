"""Sticky work rail above the composer."""

from __future__ import annotations

from textual.widgets import Static

from vera.presentation.activity import ActivityState
from vera.presentation.work_rail import project_work_rail, render_work_rail


class VeraWorkRail(Static):
    DEFAULT_CSS = """
    VeraWorkRail {
        width: 100%;
        height: auto;
        padding: 0 2;
        color: $text-muted;
        display: none;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self._activity = ActivityState("就绪", "idle", False)
        self._frame = "·"
        self._columns = 80
        self._unicode = True

    def set_activity(self, state: ActivityState, frame: str) -> None:
        self._activity = state
        self._frame = frame
        self._refresh()

    def set_geometry(self, *, columns: int, unicode: bool) -> None:
        self._columns = columns
        self._unicode = unicode
        self._refresh()

    def _refresh(self) -> None:
        rail = project_work_rail(self._activity)
        text = render_work_rail(
            rail,
            columns=self._columns,
            unicode=self._unicode,
            frame=self._frame,
        )
        self.display = bool(text)
        self.set_class(rail.active, "-active")
        self.update(text)
