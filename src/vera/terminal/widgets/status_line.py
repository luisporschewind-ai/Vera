"""Bottom status line for context, model, and reasoning."""

from __future__ import annotations

from textual.widgets import Static

from vera.presentation.activity import ActivityState
from vera.presentation.footer_status import FooterStatus, render_footer_status
from vera.session.models import SessionStatus
from vera.terminal.display import display_width, pad_display


class VeraStatusLine(Static):
    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("会话上下文", id=id)
        self._pending = 0
        self._footer: FooterStatus | None = None
        self._notice = ""
        self._columns = 80
        self._unicode = True

    @property
    def notice(self) -> str:
        return self._notice

    def set_status(self, text: str) -> None:
        self._notice = text.strip()
        self._refresh()

    def set_pending(self, count: int) -> None:
        self._pending = count
        self._refresh()

    def set_activity(self, state: ActivityState, frame: str) -> None:
        del state, frame
        self._refresh()

    def set_geometry(self, *, columns: int, unicode: bool) -> None:
        self._columns = columns
        self._unicode = unicode
        self._refresh()

    def set_footer(self, footer: FooterStatus) -> None:
        self._footer = footer
        self._refresh()

    def apply_session(
        self,
        session: SessionStatus,
        activity: ActivityState | None = None,
        *,
        unread: int = 0,
    ) -> None:
        from vera.presentation.footer_status import project_footer_status

        self._footer = project_footer_status(session, activity, unread=unread or self._pending)
        self._refresh()

    def _refresh(self) -> None:
        if self._notice and self._footer is None:
            self.update(self._notice)
            return
        if self._footer is None:
            self.update("会话上下文")
            return
        footer = self._footer
        unread = self._pending or footer.unread
        if unread != footer.unread:
            footer = footer.model_copy(update={"unread": unread})
        columns = self._content_columns()
        if self._notice:
            reserved = display_width(self._notice) + 2
            inner = max(4, columns - reserved)
            body = render_footer_status(footer, columns=inner, unicode=self._unicode)
            text = f"{self._notice}  {body}"
        else:
            text = render_footer_status(footer, columns=columns, unicode=self._unicode)
        self.update(pad_display(text, columns))

    def _content_columns(self) -> int:
        if not self.size.width:
            return max(4, self._columns - 4)
        # A resize may update the app geometry one refresh before Textual
        # publishes the widget's new size. Never render wider than the latest
        # terminal columns while that layout catches up.
        width = min(int(self.size.width), self._columns)
        try:
            padding = self.styles.padding
            inner = width - int(padding.left) - int(padding.right)
        except Exception:
            inner = width - 4
        return max(4, inner)
