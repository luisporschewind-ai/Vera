"""Bottom status line for activity and hints."""

from __future__ import annotations

from textual.widgets import Static

from vera.presentation.activity import ActivityState


class VeraStatusLine(Static):
    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("就绪 · /help 查看命令", id=id)
        self._pending = 0

    def set_status(self, text: str) -> None:
        self.update(text)

    def set_pending(self, count: int) -> None:
        self._pending = count
        if count:
            current = str(self.render())
            if "新消息" not in current:
                self.update(f"{current} · {count} 条新消息 ↓")

    def set_activity(self, state: ActivityState, frame: str) -> None:
        marker = frame if state.active else ("✓" if state.severity == "info" else "!")
        pending = f" · {self._pending} 条新消息 ↓" if self._pending else ""
        # Offering cancel after a run reached a terminal state is a false affordance.
        hint = " · Esc/Ctrl-C 取消" if state.active else " · /help 查看命令"
        self.update(f"{marker} {state.label}{hint}{pending}")
