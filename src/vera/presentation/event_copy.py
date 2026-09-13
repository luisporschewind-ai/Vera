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
    "session.status": "会话状态",
    "session.closed": "会话已关闭",
}

_FIELD_LABELS: dict[str, str] = {
    "status": "状态",
    "state": "状态",
    "outcome": "结果",
    "decision": "决定",
    "kind": "类型",
    "paths": "路径",
    "path": "路径",
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


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        if not value:
            return "无"
        if all(isinstance(item, str) for item in value):
            return "、".join(str(item) for item in value)
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
