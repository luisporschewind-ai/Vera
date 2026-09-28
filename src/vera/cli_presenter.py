"""Stable human-readable rendering for Vera Runtime events."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence

from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import event_title, format_skill_event, is_silent
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.tool_activity import READ_LABELS, ToolActivity
from vera.project_instructions import format_instruction_status
from vera.redaction import Redactor


class HumanPresenter:
    """Render authoritative Runtime events without inspecting the workspace."""

    def __init__(
        self,
        write: Callable[[str], None],
        redactor: Redactor | None = None,
        *,
        details_hint: str = "详情见运行日志",
    ) -> None:
        self._write = write
        self._details_hint = details_hint
        self._redactor = redactor or Redactor()
        self._activity: ToolActivity | None = None
        self._tool_details: list[str] = []

    def write_events(self, events: Sequence[EventEnvelope]) -> None:
        for event in events:
            self._write_event(event)

    def flush_activity(self) -> None:
        if self._activity is not None:
            self._write(self._activity.summary + f"（{self._details_hint}）")
            self._activity = None

    def write_tool_details(self) -> None:
        self._write("\n".join(self._tool_details) or "本轮暂无工具记录。")

    def approval_prompt(self, event: EventEnvelope) -> str:
        payload = self._redactor.redact(event.payload)
        if not isinstance(payload, dict):
            payload = {}
        if payload.get("kind") == "command":
            return "批准这条验证命令？输入 approve、reject 或 cancel"
        if payload.get("kind") == "recovery":
            return "批准这个恢复计划？输入 approve、reject 或 cancel"
        if payload.get("kind") == "tool":
            if payload.get("tool_name") == "request_file_access":
                return "批准上述文件访问授权？输入 approve、reject 或 cancel"
            if payload.get("tool_name") == "bash":
                return "批准执行上述命令？输入 approve、reject 或 cancel"
            return "批准上述工具操作？输入 approve、reject 或 cancel"
        return "批准这个 Change Set？输入 approve、reject 或 cancel"

    def _write_event(self, event: EventEnvelope) -> None:
        if is_silent(event.type):
            return
        raw = self._redactor.redact(event.payload)
        payload = raw if isinstance(raw, dict) else {}
        if event.type == "run.started":
            self.flush_activity()
            self._tool_details.clear()
        if event.type in {"tool.started", "tool.completed"}:
            name = str(payload.get("name", "tool"))
            error = str(payload.get("error_code") or payload.get("error") or "")
            if event.type == "tool.completed":
                self._tool_details.append(
                    sanitize_terminal_text(
                        f"{name} · {payload.get('target', '')} · "
                        f"{'成功' if payload.get('ok') else '失败'}"
                        + (f" · {error}" if error else "")
                    )
                )
                self._tool_details = self._tool_details[-200:]
            if name in READ_LABELS:
                if self._activity is None:
                    self._activity = ToolActivity()
                    self._write("正在检查项目…")
                self._activity.apply(event.model_copy(update={"payload": payload}))
                if event.type == "tool.completed" and not payload.get("ok"):
                    self.flush_activity()
                    self._write(
                        sanitize_terminal_text(
                            f"{name}：失败 · {payload.get('target', '')} · "
                            f"{error or '请查看工具结果'}"
                        )
                    )
                return
        if event.type == "tool.action_prepared":
            return
        if event.type == "tool.policy_decided":
            if payload.get("decision") == "deny":
                self.flush_activity()
                self._write("策略拒绝：" + str(payload.get("name", "tool")))
            return
        self.flush_activity()
        if event.type == "run.started":
            self._write(f"任务开始：{event.run_id}")
        elif event.type == "tool.started":
            target = payload.get("target")
            suffix = f" · {target}" if target else ""
            self._write(f"{payload.get('name', 'tool')}：执行中{suffix}")
        elif event.type == "tool.completed":
            status = "成功" if payload.get("ok") else "失败"
            target = payload.get("target")
            suffix = f" · {target}" if target else ""
            self._write(f"{payload.get('name', 'tool')}：{status}{suffix}")
        elif event.type == "session.user_prompt":
            prompt = payload.get("text")
            if isinstance(prompt, str) and prompt:
                self._write(f"你：{prompt}")
        elif event.type == "changeset.proposed":
            self._write(f"Change Set：{payload.get('content_hash', '')}")
            files = payload.get("files", [])
            if isinstance(files, list):
                for item in files:
                    if not isinstance(item, dict):
                        continue
                    self._write(f"\n{item.get('path', '')}（{item.get('operation', 'update')}）")
                    diff = item.get("unified_diff", "")
                    if isinstance(diff, str) and diff:
                        self._write(diff.rstrip("\n"))
        elif event.type == "approval.required":
            if payload.get("kind") == "command":
                argv = payload.get("argv", [])
                command = (
                    shlex.join(str(part) for part in argv) if isinstance(argv, list) else str(argv)
                )
                self._write(f"待批准的验证命令：{command}")
                self._write(f"工作目录：{payload.get('cwd', '.')}")
                profile = payload.get("artifact_profile")
                root = payload.get("artifact_root")
                if profile:
                    self._write(f"Profile：{profile}")
                if root:
                    self._write(f"产物根：{root}")
                self._write(f"风险：{payload.get('risk', 'unknown')}")
                self._write("批准仅适用于本次验证计划，执行边界由 Core 检查。")
            elif payload.get("kind") == "tool":
                tool = str(payload.get("tool_name", "unknown"))
                title = (
                    "文件访问授权"
                    if tool == "request_file_access"
                    else "命令"
                    if tool == "bash"
                    else f"工具操作：{tool}"
                )
                self._write(sanitize_terminal_text(f"待批准的{title}"))
                description = payload.get("description")
                if isinstance(description, str) and description:
                    self._write(sanitize_terminal_text(description))
                grant = payload.get("system_service_grant")
                if isinstance(grant, dict):
                    self._write("系统服务范围：仅本次；命令及全部后代继承")
                    services = grant.get("services", [])
                    if isinstance(services, list):
                        for service in services:
                            self._write(sanitize_terminal_text(f"  {service}"))
                    if grant.get("may_access_current_user_simulator_state"):
                        self._write("风险：服务可能访问当前用户的模拟器状态")
                argv = payload.get("argv")
                if isinstance(argv, list) and argv:
                    self._write(
                        sanitize_terminal_text(f"命令：{shlex.join(str(part) for part in argv)}")
                    )
                    self._write(sanitize_terminal_text(f"工作目录：{payload.get('cwd', '.')}"))
                    if payload.get("timeout_seconds") is not None:
                        self._write(f"超时：{payload['timeout_seconds']} 秒")
                self._write(f"风险：{payload.get('risk', 'unknown')}")
            elif payload.get("kind") == "recovery":
                self._write(
                    f"待批准的恢复计划：{payload.get('target_hash', '')}"
                    f"（风险：{payload.get('risk', 'unknown')}）"
                )
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
                shlex.join(str(part) for part in argv) if isinstance(argv, list) else str(argv)
            )
            self._write(f"开始验证：{command}")
        elif event.type == "verification.completed":
            status = payload.get("status", "unknown")
            reason = payload.get("reason_code")
            if reason:
                self._write(f"验证结果：{status}（{reason}）")
            else:
                self._write(f"验证结果：{status}")
            stdout = payload.get("stdout")
            stderr = payload.get("stderr")
            if isinstance(stdout, str) and stdout:
                self._write(stdout.rstrip("\n"))
            if isinstance(stderr, str) and stderr:
                self._write(stderr.rstrip("\n"))
        elif event.type in {
            "project.instructions.loaded",
            "project.instructions.skipped",
            "project.instructions.status",
        }:
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                self._write(text)
            else:
                self._write(format_instruction_status(payload))
        elif event.type in {
            "skill.listed",
            "skill.shown",
            "skill.selection.changed",
            "skill.snapshot.bound",
        }:
            self._write(format_skill_event(payload))
        elif event.type == "run.completed":
            self._write(f"任务完成：{event.run_id}（{payload.get('state', 'completed')}）")
        elif event.type == "run.failed":
            self._write(f"任务失败：{event.run_id}（{payload.get('reason', 'unknown')}）")
        elif event.type == "run.cancelled":
            self._write(f"任务已取消：{event.run_id}")
        elif event.type == "git.operation.started":
            self._write(f"Git 操作开始：{payload.get('operation', 'unknown')}")
        elif event.type == "git.operation.completed":
            self._write("Git 操作完成")
        elif event.type == "git.operation.recovered":
            self._write("Git 操作已恢复")
        elif event.type == "git.operation.manual_required":
            self._write(f"Git 操作需要人工处理：{payload.get('error_code', 'manual_required')}")
        elif event.type == "git.operation.failed":
            self._write(f"Git 操作失败：{payload.get('error_code', 'unknown')}")
        elif event.type == "rollback.completed":
            self._write(f"回滚完成：{event.run_id}")
        elif event.type == "rollback.conflicted":
            self._write(f"回滚存在冲突：{event.run_id}")
        elif event.type == "assistant.message":
            content = payload.get("content", "")
            self._write(f"Vera：{content if isinstance(content, str) else ''}")
        elif event.type == "conversation.compacted":
            summary = payload.get("summary", "")
            size = len(summary.encode("utf-8")) if isinstance(summary, str) else 0
            self._write(f"上下文已压缩（{size} bytes）")
        elif event.type == "recovery.detected":
            classification = payload.get("classification", "unknown")
            reason = payload.get("reason_code", "unknown")
            self._write(f"待恢复：{event.run_id}（{classification} / {reason}）")
            evidence = payload.get("evidence", [])
            if isinstance(evidence, list):
                for item in evidence:
                    if not isinstance(item, dict):
                        continue
                    self._write(f"{item.get('path', '')}: {item.get('state', 'unknown')}")
            actions = payload.get("allowed_actions", ())
            if isinstance(actions, list | tuple) and actions:
                self._write("允许动作：" + ", ".join(str(action) for action in actions))
        elif event.type == "recovery.resume_started":
            self._write(f"开始恢复：{event.run_id}")
        elif event.type == "recovery.resumed":
            self._write(f"已恢复到稳定边界：{event.run_id}")
        elif event.type == "recovery.abandoned":
            self._write(f"已放弃任务：{event.run_id}")
        elif event.type == "recovery.restore_proposed":
            self._write(f"恢复计划：{payload.get('recovery_hash', '')}")
            files = payload.get("files", [])
            if isinstance(files, list):
                for item in files:
                    if isinstance(item, dict):
                        self._write(f"{item.get('path', '')}: {item.get('action', 'unknown')}")
        elif event.type == "recovery.restored":
            self._write(f"部分写入已恢复：{event.run_id}")
        elif event.type == "recovery.manual_required":
            self._write(f"需要人工处理：{event.run_id}（{payload.get('reason', 'unknown')}）")
        elif event.type == "approval.invalidated":
            self._write(f"审批已失效：{payload.get('approval_id', event.run_id)}")
        elif event.type == "approval.expired":
            reason = payload.get("expiry_reason", "unknown")
            self._write(
                f"审批已过期：{payload.get('approval_id', event.run_id)}（{reason}），需要重新生成"
            )
        else:
            self._write(event_title(event.type))
