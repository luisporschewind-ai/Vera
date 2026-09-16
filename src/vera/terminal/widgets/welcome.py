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
        self._mark: BrandMark | None = None
        self._status: SessionStatus | None = None
        self._columns = 80

    def set_content(self, mark: BrandMark, status: SessionStatus, *, columns: int) -> None:
        self._mark = mark
        self._status = status
        self._columns = columns
        if columns < 80:
            self.display = False
            self.update("")
            return
        self.display = True
        self.update(_welcome_text(mark, status, columns))


def _welcome_text(mark: BrandMark, status: SessionStatus, columns: int) -> str:
    del mark
    session = "恢复会话" if status.context.source in {"continued", "resumed"} else "新会话"
    if status.context.persistent_state == "unsaved":
        session = f"{session} · 未保存"
    git = _git_label(status)
    permission = f"审批 {status.permissions.approval_mode}"
    nxt = "下一步：输入目标或 /help"
    line = f"{session} · {git} · {status.model_name} · {permission} · {nxt}"
    return clip_display(line, columns)


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
    word = mark.lines[0] if mark.lines else "VERA"
    if columns >= 80 and rows >= 24:
        clock = (now or datetime.now().astimezone()).strftime("%H:%M")
        second = f"{workspace}  {git}  {session}  {clock}"
        return f"{word}\n{clip_display(second, columns)}"
    summary = f"{word}  {workspace}  {git}"
    return clip_display(summary, columns)
