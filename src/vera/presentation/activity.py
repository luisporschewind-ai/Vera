"""Map authoritative events to human activity labels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vera.contracts import JsonValue
from vera.contracts.streaming import RuntimeOutput, StreamFrame, StreamFrameType

_STEP_LABELS = {
    "read": "读取",
    "ls": "列出",
    "grep": "搜索",
    "find": "发现",
    "write": "写入",
    "edit": "编辑",
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
        "changeset.proposed": ("处理中", "processing", True, "info"),
        "approval.required": ("等待审批", "approval", False, "warning"),
        "changeset.applied": ("处理中", "processing", True, "info"),
        "verification.started": ("正在验证", "verify", True, "info"),
        "verification.completed": ("处理中", "processing", True, "info"),
        "tool.completed": ("处理中", "processing", True, "info"),
        "tool.failed": ("处理中", "processing", True, "warning"),
        "approval.resolved": ("处理中", "processing", True, "info"),
        "recovery.detected": ("已列出待恢复任务", "recovery", False, "warning"),
        "recovery.resume_started": ("正在恢复", "recovery", True, "warning"),
        "recovery.resumed": ("已续跑", "recovery", False, "info"),
        "recovery.abandoned": ("已放弃中断任务", "recovery", False, "warning"),
        "recovery.manual_required": ("需要人工恢复", "recovery", False, "warning"),
        "git.operation.started": ("正在执行 Git 操作", "git", True, "warning"),
        "git.operation.completed": ("Git 操作已完成", "git", False, "info"),
        "git.operation.recovered": ("Git 操作已恢复", "git", False, "warning"),
        "git.operation.manual_required": ("Git 操作需要人工恢复", "git", False, "error"),
        "git.operation.failed": ("Git 操作失败", "git", False, "error"),
        "run.completed": ("已完成", "done", False, "info"),
        "run.cancelled": ("已取消", "cancelled", False, "warning"),
        "run.failed": ("失败", "failed", False, "error"),
    }

    def __init__(self) -> None:
        self._steps: tuple[str, ...] = ()
        self._target = ""
        self._run_id = ""
        self._accepting_delta = False
        self._state = ActivityState("就绪", "idle", False)

    def apply(self, event: RuntimeOutput) -> ActivityState:
        if isinstance(event, StreamFrame):
            if (
                event.type is StreamFrameType.ASSISTANT_DELTA
                and event.run_id == self._run_id
                and self._accepting_delta
                and self._state.phase not in {"done", "cancelled", "failed", "error"}
            ):
                self._state = self._emit("正在回复", "replying", True, "info")
            return self._state
        if event.type == "run.started":
            self._steps = ()
            self._target = ""
            self._run_id = event.run_id
            self._accepting_delta = False
            self._state = self._emit("处理中", "processing", True, "info")
            return self._state
        if self._run_id and event.run_id and event.run_id != self._run_id:
            return self._state
        if event.run_id and not self._run_id and event.type in self._LABELS:
            self._steps = ()
            self._target = ""
            self._run_id = event.run_id
        if event.type == "model.requested":
            self._accepting_delta = True
        elif event.type in {
            "model.completed",
            "model.failed",
            "tool.started",
            "approval.required",
            "verification.started",
            "run.completed",
            "run.cancelled",
            "run.failed",
        }:
            self._accepting_delta = False
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
        if event.type in {
            "tool.completed",
            "tool.failed",
            "changeset.proposed",
            "changeset.applied",
            "verification.completed",
        }:
            self._target = ""
        if event.type == "tool.started":
            name = str(event.payload.get("name", ""))
            if name in {"read", "read_file", "ls", "grep", "find", "list_directory", "search_text"}:
                label = "正在读取"
            elif name in {"write", "edit"}:
                label = "正在修改"
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
        self._accepting_delta = False
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
