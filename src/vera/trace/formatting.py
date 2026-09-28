"""Safe human-readable formatting for a structured RunTrace."""

from __future__ import annotations

from vera.contracts.trace import RunTrace, TraceSpan
from vera.presentation.sanitize import sanitize_terminal_text


def _duration(value: float | None) -> str:
    return "未知" if value is None else f"{value:.1f} ms"


def _status(value: str) -> str:
    return {
        "active": "运行中",
        "awaiting_approval": "等待审批",
        "completed": "已完成",
        "failed": "失败",
        "cancelled": "已取消",
        "unknown": "未知",
        "ok": "成功",
        "error": "错误",
        "rejected": "已拒绝",
        "interrupted": "中断/未知",
        "partial": "部分可用",
        "unavailable": "不可用",
        "complete": "完整",
    }.get(value, value)


def _short(value: str, limit: int = 56) -> str:
    safe = sanitize_terminal_text(value).replace("\n", " ").replace("\r", " ")
    return safe if len(safe) <= limit else safe[: limit - 1] + "…"


def _span_line(span: TraceSpan) -> str:
    label = {"llm": "模型", "tool": "工具", "verification": "验证", "context": "上下文"}[span.kind]
    details = [f"{label}: {_short(span.name)}", _status(span.status), _duration(span.duration_ms)]
    attempt = span.attributes.get("attempt")
    if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0:
        details.append(f"第 {attempt} 次尝试")
    if isinstance(span.attributes.get("retry_of_span_id"), str):
        details.append("重试")
    error_code = span.attributes.get("error_code") or span.attributes.get("reason_code")
    if isinstance(error_code, str):
        details.append(f"错误码 {_short(error_code, 32)}")
    return "  " + " · ".join(details)


def _repeated_content_bytes(trace: RunTrace) -> tuple[int, int]:
    seen: dict[tuple[str, str, str], int] = {}
    repeated_bytes = 0
    repeated_entries = 0
    for snapshot in trace.context_snapshots:
        for part in snapshot.parts:
            key = (part.kind, part.source_ref, part.content_hash)
            previous_count = seen.get(key, 0)
            per_occurrence = part.byte_count // part.occurrence_count
            repeats = max(0, part.occurrence_count - max(0, 1 - previous_count))
            repeated_entries += repeats
            repeated_bytes += repeats * per_occurrence
            seen[key] = previous_count + part.occurrence_count
    return repeated_bytes, repeated_entries


def format_run_trace(trace: RunTrace) -> str:
    """Render summaries only; never expose prompt, tool payload, or raw output."""

    usage = trace.token_usage
    token_value = (
        str(usage.total_tokens)
        if usage.total_tokens is not None
        else f"已知小计 {usage.known_token_subtotal}"
        if usage.known_token_subtotal is not None
        else "未知"
    )
    verification_spans = tuple(span for span in trace.spans if span.kind == "verification")
    verification_passed = sum(
        span.attributes.get("status") == "passed" for span in verification_spans
    )
    verification_failed = sum(
        span.attributes.get("status") == "failed" for span in verification_spans
    )
    lines = [
        f"Run ID: {_short(trace.run_id, 96)}",
        f"状态: {_status(trace.status)} · 总耗时: {_duration(trace.duration_ms)}",
        (
            f"Provider 报告 Token: {token_value}（{_status(usage.status)}） · "
            f"模型调用: {usage.calls}（未知用量 {usage.usage_unknown_calls}） · "
            f"重试: {trace.retry_count}"
        ),
        (
            f"Tool 调用: {trace.tool_call_count} · Verification 通过 {verification_passed} / "
            f"失败 {verification_failed} / 总数 {trace.verification_count}"
        ),
        "时间线:",
    ]
    if trace.spans:
        lines.extend(_span_line(span) for span in trace.spans)
    else:
        lines.append("  暂无 Span 明细。")

    slowest = max(
        (span for span in trace.spans if span.duration_ms is not None),
        key=lambda span: span.duration_ms or 0,
        default=None,
    )
    largest = max(trace.context_snapshots, key=lambda item: item.total_bytes, default=None)
    repeated_bytes, repeated_entries = _repeated_content_bytes(trace)
    lines.append(
        "最慢操作: "
        + (
            f"{_short(slowest.name)} · {_duration(slowest.duration_ms)}"
            if slowest is not None
            else "未知"
        )
    )
    lines.append(
        "最大请求 Context: " + (f"{largest.total_bytes} bytes" if largest is not None else "未知")
    )
    lines.append(f"重复发送内容: {repeated_bytes} bytes · {repeated_entries} 项")
    if trace.completeness != "complete":
        lines.append(f"注意: Trace {_status(trace.completeness)}。")
    if usage.status != "complete":
        lines.append("注意: Provider Token 用量存在缺失；未知值未按 0 计算。")
    if trace.diagnostic_codes:
        lines.append("诊断: " + ", ".join(_short(code, 48) for code in trace.diagnostic_codes))
    if any(snapshot.truncated for snapshot in trace.context_snapshots):
        lines.append("注意: Context 明细超过保留上限，汇总字节数仍来自完整快照。")
    return sanitize_terminal_text("\n".join(lines))
