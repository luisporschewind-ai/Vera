"""Stable human-readable rendering for Vera Runtime events."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence

from vera.contracts.events import EventEnvelope


class HumanPresenter:
    """Render authoritative Runtime events without inspecting the workspace."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write

    def write_events(self, events: Sequence[EventEnvelope]) -> None:
        for event in events:
            self._write_event(event)

    def approval_prompt(self, event: EventEnvelope) -> str:
        if event.payload.get("kind") == "command":
            return "批准这条验证命令？输入 approve、reject 或 cancel"
        return "批准这个 Change Set？输入 approve、reject 或 cancel"

    def _write_event(self, event: EventEnvelope) -> None:
        payload = event.payload
        if event.type == "run.started":
            self._write(f"任务开始：{event.run_id}")
        elif event.type == "tool.started":
            self._write(f"{payload.get('name', 'tool')}：执行中")
        elif event.type == "tool.completed":
            status = "成功" if payload.get("ok") else "失败"
            self._write(f"{payload.get('name', 'tool')}：{status}")
        elif event.type == "changeset.proposed":
            self._write(f"Change Set：{payload.get('content_hash', '')}")
            files = payload.get("files", [])
            if isinstance(files, list):
                for item in files:
                    if not isinstance(item, dict):
                        continue
                    self._write(
                        f"\n{item.get('path', '')}（{item.get('operation', 'update')}）"
                    )
                    diff = item.get("unified_diff", "")
                    if isinstance(diff, str) and diff:
                        self._write(diff.rstrip("\n"))
        elif event.type == "approval.required":
            if payload.get("kind") == "command":
                argv = payload.get("argv", [])
                command = (
                    shlex.join(str(part) for part in argv)
                    if isinstance(argv, list)
                    else str(argv)
                )
                self._write(f"待批准的验证命令：{command}")
                self._write(f"工作目录：{payload.get('cwd', '.')}")
                self._write(f"风险：{payload.get('risk', 'unknown')}")
                self._write("该进程以当前系统用户权限运行，Vera 第一版不提供 OS 沙箱。")
            else:
                self._write(
                    f"待批准的 Change Set：{payload.get('target_hash', '')}"
                    f"（风险：{payload.get('risk', 'unknown')}）"
                )
        elif event.type == "approval.resolved":
            self._write(f"审批结果：{payload.get('decision', 'unknown')}")
        elif event.type == "checkpoint.created":
            self._write(f"Checkpoint 已创建：{payload.get('checkpoint_id', event.run_id)}")
        elif event.type == "changeset.applied":
            self._write("Change Set 已应用")
        elif event.type == "verification.started":
            argv = payload.get("argv", [])
            command = (
                shlex.join(str(part) for part in argv)
                if isinstance(argv, list)
                else str(argv)
            )
            self._write(f"开始验证：{command}")
        elif event.type == "verification.completed":
            self._write(f"验证结果：{payload.get('status', 'unknown')}")
            stdout = payload.get("stdout")
            stderr = payload.get("stderr")
            if isinstance(stdout, str) and stdout:
                self._write(stdout.rstrip("\n"))
            if isinstance(stderr, str) and stderr:
                self._write(stderr.rstrip("\n"))
        elif event.type == "run.completed":
            self._write(f"任务完成：{event.run_id}（{payload.get('state', 'completed')}）")
        elif event.type == "run.failed":
            self._write(f"任务失败：{event.run_id}（{payload.get('reason', 'unknown')}）")
        elif event.type == "run.cancelled":
            self._write(f"任务已取消：{event.run_id}")
        elif event.type == "rollback.completed":
            self._write(f"回滚完成：{event.run_id}")
        elif event.type == "rollback.conflicted":
            self._write(f"回滚存在冲突：{event.run_id}")
        else:
            self._write(event.type)
