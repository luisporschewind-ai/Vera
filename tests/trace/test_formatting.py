from vera.contracts.trace import (
    ContextKindTotal,
    ContextPart,
    ContextSnapshot,
    RunTrace,
    TraceSpan,
    TraceTokenUsage,
)
from vera.trace.formatting import format_run_trace


def _snapshot(request_index: int, byte_count: int) -> ContextSnapshot:
    part = ContextPart(
        kind="user_input",
        source_ref="run_goal",
        content_hash="a" * 64,
        byte_count=byte_count,
        occurrence_count=1,
        message_count=1,
        schema_count=0,
    )
    return ContextSnapshot(
        snapshot_id=f"snapshot_{request_index}",
        request_index=request_index,
        total_bytes=byte_count,
        context_budget_bytes=1000,
        message_count=1,
        tool_schema_count=0,
        parts=(part,),
        by_kind=(ContextKindTotal(kind="user_input", byte_count=byte_count, entry_count=1),),
        truncated=False,
        omitted_entry_count=0,
        omitted_bytes=0,
    )


def test_format_run_trace_labels_local_byte_facts_and_repeated_content() -> None:
    trace = RunTrace(
        run_id="run_safe",
        trace_id="run_safe",
        started_at=None,
        finished_at=None,
        duration_ms=None,
        status="unknown",
        spans=(
            TraceSpan(
                span_id="span_2",
                trace_id="run_safe",
                kind="llm",
                name="provider attempt",
                started_at=None,
                finished_at=None,
                duration_ms=4.0,
                status="ok",
                attributes={"attempt": 2, "retry_of_span_id": "span_1"},
            ),
        ),
        context_snapshots=(_snapshot(1, 10), _snapshot(2, 10)),
        token_usage=TraceTokenUsage(
            status="unavailable",
            calls=0,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cache_hit_input_tokens=None,
            cache_miss_input_tokens=None,
            known_token_subtotal=None,
            usage_unknown_calls=0,
        ),
        retry_count=0,
        tool_call_count=0,
        verification_count=0,
        completeness="unknown",
        diagnostic_codes=(),
    )

    text = format_run_trace(trace)

    assert "重复发送内容: 10 bytes · 1 项" in text
    assert "Provider 报告 Token: 未知（不可用）" in text
    assert "最大请求 Context: 10 bytes" in text
    assert "第 2 次尝试" in text
    assert "重试" in text
