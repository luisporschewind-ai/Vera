"""Actionable failure copy. Presenters do not invent success or permission."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from vera.contracts.events import EventEnvelope

type SideEffectFact = Literal["workspace_changed", "no_workspace_change", "unknown"]

_REASON_TEXT: dict[str, str] = {
    "model_error": "模型调用失败",
    "max_model_turns": "达到本次任务的模型往返上限",
    "max_context_bytes": "上下文超出预算，压缩后仍然超限",
    "max_tool_calls": "达到本次任务的工具调用上限",
    "empty_model_response": "模型返回了空响应",
    "invalid_compaction_response": "模型返回的压缩结果不可用",
    "repeated_tool_call": "模型重复了同一次工具调用",
    "missing_changeset": "模型没有给出可应用的 Change Set",
    "no_changes_proposed": "模型没有提出任何改动",
    "missing_recovery_plan": "缺少可用的恢复计划",
    "checkpoint_failed": "创建检查点失败",
    "provider_timeout": "模型请求超时",
    "provider_authentication_error": "模型供应商认证失败",
    "provider_rate_limited": "模型供应商限流",
    "provider_network_error": "无法连接模型供应商",
    "provider_request_invalid": "发给模型供应商的请求不被接受",
    "provider_service_error": "模型供应商返回服务错误",
}


def describe_reason(reason: str) -> str:
    """Render a stable reason code as human copy while keeping the code visible."""

    text = _REASON_TEXT.get(reason) or _REASON_TEXT.get(reason.split(":", 1)[0])
    return f"{text}（{reason}）" if text else reason


def _failed_side_effects(side_effects: SideEffectFact) -> tuple[str, str]:
    if side_effects == "no_workspace_change":
        return (
            "未产生工作区变化，不需要回滚。",
            "可以修正目标或配置后重试。",
        )
    if side_effects == "workspace_changed":
        return (
            "已写入工作区变更。",
            "使用 /diff 复核改动，必要时 /rollback 回滚。",
        )
    return (
        "可能已产生部分工作区或状态变化。",
        "查看 /runs 与 /recover，必要时回滚。",
    )


def format_diagnostics(diagnostics: Mapping[str, object] | None) -> str:
    """Surface provider failure detail that would otherwise only exist in logs."""

    if not diagnostics:
        return ""
    parts: list[str] = []
    code = diagnostics.get("code")
    if code:
        parts.append(f"供应商 code {code}")
    status_code = diagnostics.get("status_code")
    if status_code is not None:
        parts.append(f"HTTP {status_code}")
    detail = diagnostics.get("detail") or diagnostics.get("message")
    if isinstance(detail, str) and detail:
        parts.append(detail)
    retry_after = diagnostics.get("retry_after_seconds")
    if retry_after is not None:
        parts.append(f"建议 {retry_after}s 后重试")
    return " · ".join(parts)


def explain_failure(
    event: EventEnvelope,
    *,
    side_effects: SideEffectFact = "unknown",
) -> dict[str, str]:
    event_type = event.type
    # Falling back to the event type would leak an internal identifier into copy.
    raw_reason = str(event.payload.get("reason") or event.payload.get("message") or "")
    reason = describe_reason(raw_reason) if raw_reason else "原因未记录"
    if event_type == "run.cancelled":
        if side_effects == "no_workspace_change":
            return {
                "what": "用户取消了当前任务。",
                "side_effects": "已取消后续动作，未产生工作区变化。",
                "next": "可以继续对话或重新发起任务。",
            }
        return {
            "what": "用户取消了当前任务。",
            "side_effects": "已取消后续动作；已写入的变更需要单独回滚。",
            "next": "可继续对话，或使用 /rollback 查看可回滚任务。",
        }
    if event_type == "approval.expired":
        return {
            "what": "审批已过期，不能使用原来的决定。",
            "side_effects": "没有应用这次过期审批。",
            "next": "请重新生成审批后再决定。",
        }
    if event_type == "run.failed":
        effects, next_step = _failed_side_effects(side_effects)
        return {
            "what": f"任务失败：{reason}",
            "side_effects": effects,
            "next": next_step,
        }
    if event_type.startswith("recovery."):
        return {
            "what": f"恢复未完成：{reason}",
            "side_effects": "工作区可能仍处于中断状态。",
            "next": "使用 /recover 查看分类后再 /resume 或 /abandon。",
        }
    return {
        "what": f"发生错误：{reason}",
        "side_effects": "副作用未知，不要假设已经成功。",
        "next": "使用 /help 或 /doctor 查看下一步。",
    }


def format_failure_body(
    event: EventEnvelope,
    *,
    side_effects: SideEffectFact = "unknown",
    diagnostics: Mapping[str, object] | None = None,
) -> str:
    explained = explain_failure(event, side_effects=side_effects)
    lines = [
        f"发生了什么：{explained['what']}",
        f"是否有副作用：{explained['side_effects']}",
    ]
    detail = format_diagnostics(diagnostics)
    if detail:
        lines.append(f"诊断：{detail}")
    lines.append(f"下一步：{explained['next']}")
    return "\n".join(lines)
