"""Actionable failure copy. Presenters do not invent success or permission."""

from __future__ import annotations

from vera.contracts.events import EventEnvelope


def explain_failure(event: EventEnvelope) -> dict[str, str]:
    event_type = event.type
    reason = str(event.payload.get("reason") or event.payload.get("message") or event_type)
    if event_type == "run.cancelled":
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
        return {
            "what": f"任务失败：{reason}",
            "side_effects": "可能已产生部分工作区或状态变化。",
            "next": "查看 /runs 与 /recover，必要时回滚。",
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


def format_failure_body(event: EventEnvelope) -> str:
    explained = explain_failure(event)
    return (
        f"发生了什么：{explained['what']}\n"
        f"是否有副作用：{explained['side_effects']}\n"
        f"下一步：{explained['next']}"
    )
