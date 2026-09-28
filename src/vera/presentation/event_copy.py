"""Human-facing copy for authoritative events.

Internal event type names and raw payload dicts must never reach a user-facing
surface. Protocol field names keep their canonical spelling, which is allowed;
event type identifiers are not.
"""

from __future__ import annotations

from collections.abc import Mapping

# Model round trips are already represented by the status-line activity, so they
# would only add noise as timeline blocks. model.failed detail is folded into the
# terminal failure card instead of standing alone.
SILENT_EVENT_TYPES = frozenset(
    {
        "model.requested",
        "model.completed",
        "model.retrying",
        "model.failed",
        "security.findings_truncated",
    }
)

_TITLES: dict[str, str] = {
    "tool.repetition_detected": "多次读取未获得新信息，正在检查是否重复调查",
    "tool.policy_decided": "工具策略判定",
    "run.started": "任务已开始",
    "checkpoint.created": "已创建检查点",
    "checkpoint.restored": "已恢复检查点",
    "checkpoint.restore_failed": "检查点恢复失败",
    "changeset.applied": "已写入变更",
    "approval.resolved": "审批已决定",
    "conversation.compacted": "已压缩上下文",
    "security.content_flagged": "检测到可疑内容",
    "rollback.completed": "已回滚",
    "rollback.conflicted": "回滚存在冲突",
    "recovery.detected": "发现可恢复任务",
    "recovery.abandoned": "已放弃中断任务",
    "recovery.manual_required": "需要人工恢复",
    "recovery.restored": "已恢复",
    "recovery.restore_proposed": "提出恢复方案",
    "recovery.resume_started": "开始续跑",
    "recovery.resumed": "已续跑",
    "state.inspected": "已检查状态",
    "state.migration_completed": "状态迁移完成",
    "run.completed": "任务完成",
    "git.operation.started": "开始 Git 操作",
    "git.operation.completed": "Git 操作完成",
    "git.operation.recovered": "Git 操作已恢复",
    "git.operation.manual_required": "Git 操作需要人工恢复",
    "git.operation.failed": "Git 操作失败",
    "session.status": "会话状态",
    "session.closed": "会话已关闭",
    "session.message": "会话",
    "session.help": "帮助",
    "session.doctor": "诊断",
    "session.theme": "主题",
    "session.shortcuts": "快捷键",
    "session.config": "配置",
    "session.usage": "用量",
    "session.permissions": "权限",
    "session.review": "审查",
    "session.diff": "Diff",
    "session.persistence_changed": "会话未保存",
    "session.close_warning": "退出前警告",
    "session.loaded": "已恢复会话",
    "session.listed": "会话列表",
    "session.load_failed": "会话恢复失败",
    "project.instructions.loaded": "已加载项目指令",
    "project.instructions.skipped": "已跳过项目指令",
    "project.instructions.status": "项目指令",
}

_FIELD_LABELS: dict[str, str] = {
    "status": "状态",
    "state": "状态",
    "outcome": "结果",
    "decision": "决定",
    "kind": "类型",
    "paths": "路径",
    "path": "路径",
    "target": "目标",
    "name": "动作",
    "files": "文件数",
    "checkpoint_id": "检查点",
    "changeset_id": "Change Set",
    "approval_id": "审批",
    "classification": "分类",
    "reason": "原因",
    "reason_code": "原因",
    "risk": "风险",
    "source_kind": "来源",
    "trust_level": "信任级别",
    "finding_count": "命中数",
    "before_bytes": "压缩前字节",
    "after_bytes": "压缩后字节",
    "message_count": "消息数",
    "format_status": "格式状态",
}

_TOOL_ACTIONS = {
    "write": "写入文件",
    "edit": "编辑文件",
    "read_file": "读取文件",
    "list_directory": "列出目录",
    "search_text": "搜索文本",
    "propose_changeset": "提出变更",
}

_TOOL_STATUS = {
    "running": "进行中",
    "completed": "完成",
    "failed": "失败",
}

_CLASSIFICATION_TEXT = {
    "resumable_approval": "可续跑（等待审批）",
    "resumable_verification": "可续跑（等待验证）",
    "recoverable_partial_apply": "部分写入，可还原",
    "safe_to_abandon": "可安全放弃",
    "manual_required": "需要人工处理",
    "legacy_not_resumable": "旧格式，不可续跑",
}

_RECOVERY_REASON_TEXT = {
    "awaiting_changeset_approval": "任务中断在变更审批",
    "awaiting_verification": "任务中断在验证",
    "recoverable_partial_apply": "部分文件已写入",
    "safe_to_abandon": "工作区未写入，可放弃",
    "manual_required": "无法自动判断恢复方式",
    "legacy_not_resumable": "缺少可恢复快照",
    "identity_mismatch": "工作区身份与快照不一致",
    "workspace_missing": "工作区不可用",
    "verification_in_flight": "验证进行中被中断",
    "rollback_in_flight": "回滚进行中被中断",
    "evidence_conflict": "工作区证据与快照冲突",
    "unknown_hash": "文件哈希无法核对",
    "checkpoint_missing": "缺少检查点",
    "unsupported_version": "状态版本不受支持",
    "invalid_snapshot": "快照无效或损坏",
    "missing_journal": "缺少事件日志",
    "not_resumable": "当前分类不可续跑",
    "git_operation_pending": "Git 操作中断，等待恢复判断",
}

_RECOVERY_ACTION_COMMANDS = {
    "resume": "/resume {run_id}",
    "abandon": "/abandon {run_id}",
    "rollback": "/rollback {run_id}",
    "restore": "/resume {run_id}",
}


def tool_action_label(name: str) -> str:
    return _TOOL_ACTIONS.get(name, name)


def format_tool_title(
    name: str,
    *,
    target: str = "",
    status: str,
    duration_ms: int | None = None,
) -> str:
    action = tool_action_label(name)
    status_label = _TOOL_STATUS.get(status, status)
    head = f"{action}  {target}".rstrip() if target else action
    tail = [status_label]
    if duration_ms is not None:
        tail.append(f"{duration_ms}ms")
    return f"{head}  · " + " · ".join(tail)


def format_tool_body(
    *,
    target: str = "",
    status: str,
    duration_ms: int | None = None,
    error: str = "",
    error_code: str = "",
    truncated: bool = False,
) -> str:
    lines: list[str] = []
    if target:
        lines.append(f"目标：{target}")
    lines.append(f"状态：{_TOOL_STATUS.get(status, status)}")
    if duration_ms is not None:
        lines.append(f"耗时：{duration_ms}ms")
    if error:
        lines.append(f"错误：{error}")
    if error_code:
        lines.append(f"错误码：{error_code}")
    if truncated:
        lines.append("输出已截断")
    return "\n".join(lines)


# Identifiers and hashes are useful in logs but only clutter a timeline summary.
_HIDDEN_FIELDS = frozenset(
    {
        "run_id",
        "sequence",
        "event_id",
        "goal",
        "goal_hash",
        "goal_bytes",
        "target_hash",
        "content_hash",
        "policy_hash",
        "target_id",
        "plan_id",
        "expected_head_oid",
        "expected_branch",
        "call_id",
        "workspace_root",
        "text",
    }
)


def is_silent(event_type: str) -> bool:
    return event_type in SILENT_EVENT_TYPES


def event_title(event_type: str) -> str:
    """Return human copy for an event type, never the identifier itself."""

    return _TITLES.get(event_type, "状态更新")


def classification_label(value: str) -> str:
    text = _CLASSIFICATION_TEXT.get(value)
    return f"{text}（{value}）" if text else value


def recovery_reason_label(value: str) -> str:
    text = _RECOVERY_REASON_TEXT.get(value)
    return f"{text}（{value}）" if text else value


def format_recovery_inspection(run_id: str, payload: Mapping[str, object]) -> str:
    """Render a read-only recovery report, including the run-id needed for next commands."""

    reported_id = str(payload.get("run_id") or run_id)
    lines = [f"run-id：{reported_id}"]
    classification = payload.get("classification")
    if isinstance(classification, str) and classification:
        lines.append(f"分类：{classification_label(classification)}")
    stage = payload.get("stage")
    if isinstance(stage, str) and stage:
        lines.append(f"阶段：{stage}")
    reason = payload.get("reason_code") or payload.get("reason")
    if isinstance(reason, str) and reason:
        lines.append(f"原因：{recovery_reason_label(reason)}")
    workspace = payload.get("workspace_root")
    if isinstance(workspace, str) and workspace:
        lines.append(f"工作区：{workspace}")
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            state = item.get("state")
            if isinstance(path, str) and path:
                suffix = f"：{state}" if isinstance(state, str) and state else ""
                lines.append(f"证据：{path}{suffix}")
    next_step = _recovery_next_step(
        reported_id,
        payload.get("allowed_actions"),
        classification if isinstance(classification, str) else "",
    )
    lines.append(f"下一步：{next_step}")
    return "\n".join(lines)


def _recovery_next_step(run_id: str, actions: object, classification: str = "") -> str:
    if not isinstance(actions, list | tuple):
        return "当前分类没有可执行的恢复命令。"
    commands: list[str] = []
    for action in actions:
        if not isinstance(action, str) or action in {"inspect", "rerun"}:
            continue
        template = _RECOVERY_ACTION_COMMANDS.get(action)
        if template is None:
            continue
        command = template.format(run_id=run_id)
        if command not in commands:
            commands.append(command)
    if "rerun" in actions:
        commands.append("重新发起任务")
    if commands:
        return " 或 ".join(commands)
    if classification == "manual_required":
        return "不能自动 /resume 或 /abandon。请核对上面的证据文件；Vera 不会改写工作区。"
    return "当前分类没有可执行的恢复命令。"


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        if not value:
            return "无"
        if all(isinstance(item, str) for item in value):
            return "、".join(str(item) for item in value)
        if all(isinstance(item, dict) for item in value):
            rendered: list[str] = []
            for item in value:
                name = item.get("name") or item.get("keys") or item.get("path")
                extra = item.get("detail") or item.get("action") or item.get("status")
                if name and extra:
                    rendered.append(f"{name} {extra}")
                elif name:
                    rendered.append(str(name))
            if rendered:
                return "；".join(str(part) for part in rendered)
        return str(len(value))
    if isinstance(value, dict):
        return str(len(value))
    if value is None:
        return "无"
    return str(value)


def event_summary(payload: Mapping[str, object]) -> str:
    """Render a payload as labelled lines rather than a raw dict repr."""

    lines: list[str] = []
    for key, value in payload.items():
        if key in _HIDDEN_FIELDS:
            continue
        label = _FIELD_LABELS.get(key, key)
        lines.append(f"{label}：{_render_value(value)}")
    return "\n".join(lines)
