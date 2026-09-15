"""Map authoritative events to human activity labels."""

from __future__ import annotations

from dataclasses import dataclass

from vera.contracts.events import EventEnvelope


@dataclass(frozen=True, slots=True)
class ActivityState:
    label: str
    phase: str
    active: bool
    severity: str = "info"


class ActivityPresenter:
    _LABELS = {
        "model.requested": ("正在思考", "thinking", True, "info"),
        "tool.started": ("正在读取", "tool", True, "info"),
        "changeset.proposed": ("正在规划修改", "planning", True, "info"),
        "approval.required": ("等待审批", "approval", True, "warning"),
        "changeset.applied": ("正在验证", "verify", True, "info"),
        "verification.started": ("正在验证", "verify", True, "info"),
        "recovery.detected": ("已列出待恢复任务", "recovery", False, "warning"),
        "recovery.resume_started": ("正在恢复", "recovery", True, "warning"),
        "recovery.resumed": ("已续跑", "recovery", False, "info"),
        "recovery.abandoned": ("已放弃中断任务", "recovery", False, "warning"),
        "recovery.manual_required": ("需要人工恢复", "recovery", False, "warning"),
        "run.completed": ("已完成", "done", False, "info"),
        "run.cancelled": ("已取消", "cancelled", False, "warning"),
        "run.failed": ("失败", "failed", False, "error"),
    }

    def __init__(self) -> None:
        self._state = ActivityState("就绪", "idle", False)

    def apply(self, event: EventEnvelope) -> ActivityState:
        mapped = self._LABELS.get(event.type)
        if mapped is None:
            if event.type == "tool.started" and event.payload.get("name") == "propose_changeset":
                self._state = ActivityState("正在规划修改", "planning", True, "info")
            return self._state
        label, phase, active, severity = mapped
        if event.type == "tool.started":
            name = str(event.payload.get("name", ""))
            if name in {"read_file", "list_directory", "search_text"}:
                label = "正在读取"
            elif name == "propose_changeset":
                label = "正在规划修改"
        self._state = ActivityState(label, phase, active, severity)
        return self._state

    def reset(self) -> None:
        self._state = ActivityState("就绪", "idle", False)

    @property
    def current(self) -> ActivityState:
        return self._state
