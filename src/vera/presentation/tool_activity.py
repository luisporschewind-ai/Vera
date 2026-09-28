"""Bounded tool activity projection shared by plain and interactive clients."""

from collections import Counter

from vera.contracts.events import EventEnvelope
from vera.presentation.sanitize import sanitize_terminal_text

READ_LABELS = {
    "read": "读取",
    "read_file": "读取",
    "ls": "列目录",
    "list_directory": "列目录",
    "grep": "搜索",
    "find": "查找",
    "search_text": "搜索",
}


class ToolActivity:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.details: list[str] = []
        self.target = ""
        self.failed = False
        self.pending: set[str] = set()

    def apply(self, event: EventEnvelope) -> None:
        name = str(event.payload.get("name", "tool"))
        self.target = sanitize_terminal_text(str(event.payload.get("target") or ""))
        call_id = str(event.payload.get("call_id", event.sequence))
        if event.type == "tool.started":
            self.counts[READ_LABELS.get(name, name)] += 1
            self.pending.add(call_id)
        else:
            if not self.counts:
                self.counts[READ_LABELS.get(name, name)] += 1
            self.pending.discard(call_id)
            ok = bool(event.payload.get("ok", True))
            self.failed |= not ok
            status = "成功" if ok else "失败"
            error = str(event.payload.get("error_code") or event.payload.get("error") or "")
            self.details.append(
                sanitize_terminal_text(f"{name} · {self.target} · {status} {error}")
            )
            self.details = self.details[-200:]

    @property
    def summary(self) -> str:
        return "检查项目 · " + " / ".join(
            f"{name} {count} 次" for name, count in self.counts.items()
        )

    @property
    def body(self) -> str:
        lines = self.details[:]
        if self.pending:
            lines.append(f"正在处理：{self.target}")
        return "\n".join(lines)
