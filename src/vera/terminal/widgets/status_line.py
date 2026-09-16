"""Bottom status line for context, model, reasoning, and activity."""

from __future__ import annotations

from textual.widgets import Static

from vera.presentation.activity import ActivityState
from vera.presentation.footer_status import FooterStatus, render_footer_status
from vera.session.models import SessionStatus


class VeraStatusLine(Static):
    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("就绪 · /help 查看命令", id=id)
        self._pending = 0
        self._footer: FooterStatus | None = None
        self._activity = ActivityState("就绪", "idle", False)
        self._frame = "·"
        self._columns = 80
        self._unicode = True

    def set_status(self, text: str) -> None:
        if self._footer is None:
            self.update(text)
            return
        self._activity = ActivityState(
            text,
            self._activity.phase,
            self._activity.active,
            self._activity.severity,
        )
        self._refresh()

    def set_pending(self, count: int) -> None:
        self._pending = count
        self._refresh()

    def set_activity(self, state: ActivityState, frame: str) -> None:
        self._activity = state
        self._frame = frame
        self._refresh()

    def set_geometry(self, *, columns: int, unicode: bool) -> None:
        self._columns = columns
        self._unicode = unicode
        self._refresh()

    def set_footer(self, footer: FooterStatus) -> None:
        self._footer = footer
        self._activity = ActivityState(
            footer.activity_label,
            "idle" if not footer.activity_active else "running",
            footer.activity_active,
            footer.activity_severity,
        )
        self._refresh()

    def apply_session(
        self,
        session: SessionStatus,
        activity: ActivityState,
        *,
        unread: int = 0,
    ) -> None:
        from vera.presentation.footer_status import project_footer_status

        self._footer = project_footer_status(session, activity, unread=unread or self._pending)
        self._activity = activity
        self._refresh()

    def _refresh(self) -> None:
        if self._footer is None:
            pending = f" · {self._pending} 条新消息 ↓" if self._pending else ""
            if not self._activity.active and self._activity.label == "就绪":
                self.update(f"就绪 · /help 查看命令{pending}")
                return
            idle_mark = "✓" if self._activity.severity == "info" else "!"
            marker = self._frame if self._activity.active else idle_mark
            hint = " · Esc/Ctrl-C 取消" if self._activity.active else " · /help 查看命令"
            self.update(f"{marker} {self._activity.label}{hint}{pending}")
            return
        footer = self._footer
        if self._pending and footer.unread != self._pending:
            footer = footer.model_copy(update={"unread": self._pending})
        self.update(
            render_footer_status(
                footer,
                columns=self._columns,
                unicode=self._unicode,
                frame=self._frame,
            )
        )
