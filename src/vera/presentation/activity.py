"""Map authoritative events to human activity labels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vera.contracts import JsonValue
from vera.contracts.events import EventEnvelope

_STEP_LABELS = {
    "read_file": "读取",
    "list_directory": "列出",
    "search_text": "搜索",
    "propose_changeset": "提出变更",
}


@dataclass(frozen=True, slots=True)
class ActivityState:
    label: str
    phase: str
    active: bool
    severity: str = "info"
    target: str = ""
    steps: tuple[str, ...] = ()


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
        self._steps: tuple[str, ...] = ()
        self._target = ""
        self._run_id = ""
        self._state = ActivityState("就绪", "idle", False)

    def apply(self, event: EventEnvelope) -> ActivityState:
        if event.type == "run.started":
            self._steps = ()
            self._target = ""
            self._run_id = event.run_id
            self._state = self._emit("就绪", "idle", False, "info")
            return self._state
        if event.run_id and event.run_id != self._run_id and event.type in self._LABELS:
            self._steps = ()
            self._target = ""
            self._run_id = event.run_id
        if event.type == "tool.started":
            name = str(event.payload.get("name", ""))
            step = _STEP_LABELS.get(name)
            if step and (not self._steps or self._steps[-1] != step):
                self._steps = (*self._steps, step)
            target = _event_target(event.payload)
            if target:
                self._target = target
        mapped = self._LABELS.get(event.type)
        if mapped is None:
            if event.type == "tool.started" and event.payload.get("name") == "propose_changeset":
                self._state = self._emit("正在规划修改", "planning", True, "info")
            return self._state
        label, phase, active, severity = mapped
        if event.type == "tool.started":
            name = str(event.payload.get("name", ""))
            if name in {"read_file", "list_directory", "search_text"}:
                label = "正在读取"
            elif name == "propose_changeset":
                label = "正在规划修改"
        if not active and event.type in {"run.completed", "run.cancelled"}:
            self._target = ""
        self._state = self._emit(label, phase, active, severity)
        return self._state

    def reset(self) -> None:
        self._steps = ()
        self._target = ""
        self._run_id = ""
        self._state = ActivityState("就绪", "idle", False)

    def set_failed(self, label: str) -> ActivityState:
        self._state = self._emit(label, "error", False, "error")
        return self._state

    def _emit(self, label: str, phase: str, active: bool, severity: str) -> ActivityState:
        return ActivityState(
            label,
            phase,
            active,
            severity,
            target=self._target,
            steps=self._steps,
        )

    @property
    def current(self) -> ActivityState:
        return self._state


def _event_target(payload: Mapping[str, JsonValue]) -> str:
    for key in ("target", "path", "query"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
