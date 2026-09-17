"""Startup chrome: identifier plus workspace/session/permission facts."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from vera.session.models import SessionStatus
from vera.terminal.brand import BrandMark
from vera.terminal.display import clip_display


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


def _git_label(status: SessionStatus) -> str:
    git = status.git
    if not git.available:
        return "非 Git"
    branch = git.branch or "unknown"
    if git.dirty:
        return f"{branch}*"
    return branch


def brand_header_text(
    mark: BrandMark,
    status: SessionStatus,
    *,
    columns: int,
    rows: int = 24,
    now: datetime | None = None,
) -> str:
    workspace = status.workspace.name or str(status.workspace)
    git = _git_label(status)
    session = "已恢复" if status.context.source in {"continued", "resumed"} else "新会话"
    permission = f"审批 {status.permissions.approval_mode}"
    clock = (now or datetime.now().astimezone()).strftime("%H:%M")
    session_bits = [session]
    if status.context.persistent_state == "unsaved":
        session_bits.append("未保存")
    session_text = " · ".join(session_bits)
    word = mark.lines[0] if mark.lines else "VERA"
    if columns >= 80 and rows >= 24:
        second = f"{workspace}  {git}  {session_text}  {permission}  {clock}"
        return f"{word}\n{clip_display(second, columns)}"
    summary = f"{word}  {workspace}  {git}  {session_text}"
    return clip_display(summary, columns)
