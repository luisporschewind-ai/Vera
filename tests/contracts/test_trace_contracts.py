from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vera.contracts.trace import (
    ContextKindTotal,
    ContextPart,
    ContextSnapshot,
    RunTrace,
    TraceSpan,
    TraceTokenUsage,
)


def _valid_span(**updates: object) -> TraceSpan:
    values: dict[str, object] = {
        "span_id": "span_1",
        "trace_id": "run_1",
        "parent_span_id": None,
        "kind": "llm",
        "name": "model.attempt",
        "started_at": datetime(2026, 9, 26, 0, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 9, 26, 0, 0, 1, tzinfo=UTC),
        "duration_ms": 1000.0,
        "status": "ok",
        "attributes": {"attempt": 1},
        "event_ids": ("event_1", "event_2"),
    }
    values.update(updates)
    return TraceSpan.model_validate(values)


def test_trace_contracts_round_trip_and_normalize_aware_timestamps_to_utc() -> None:
    offset_time = datetime(2026, 9, 26, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    span = _valid_span(started_at=offset_time)

    assert span.started_at == datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    assert TraceSpan.model_validate_json(span.model_dump_json()) == span

    snapshot = ContextSnapshot(
        snapshot_id="snapshot_1",
        request_index=1,
        total_bytes=16,
        context_budget_bytes=1024,
        message_count=1,
        tool_schema_count=0,
        parts=(
            ContextPart(
                kind="user_input",
                source_ref="run_goal",
                content_hash="a" * 64,
                byte_count=16,
                occurrence_count=1,
                message_count=1,
                schema_count=0,
                truncated=False,
            ),
        ),
        by_kind=(ContextKindTotal(kind="user_input", byte_count=16, entry_count=1),),
        truncated=False,
        omitted_entry_count=0,
        omitted_bytes=0,
    )
    usage = TraceTokenUsage(
        status="unavailable",
        calls=0,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        cache_hit_input_tokens=None,
        cache_miss_input_tokens=None,
        known_token_subtotal=None,
        usage_unknown_calls=0,
    )
    trace = RunTrace(
        run_id="run_1",
        trace_id="run_1",
        session_id=None,
        started_at=datetime(2026, 9, 26, 0, 0, tzinfo=UTC),
        finished_at=None,
        duration_ms=None,
        status="active",
        spans=(span,),
        context_snapshots=(snapshot,),
        token_usage=usage,
        retry_count=0,
        tool_call_count=0,
        verification_count=0,
        completeness="partial",
        diagnostic_codes=("run_incomplete",),
    )
    assert RunTrace.model_validate_json(trace.model_dump_json()) == trace


def test_trace_span_rejects_unknown_fields_and_invalid_enum_values() -> None:
    with pytest.raises(ValidationError):
        _valid_span(unexpected="not part of the contract")
    with pytest.raises(ValidationError):
        _valid_span(kind="planner")
    with pytest.raises(ValidationError):
        _valid_span(status="success")


def test_trace_contracts_reject_negative_counts_durations_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        _valid_span(duration_ms=-1.0)
    with pytest.raises(ValidationError):
        _valid_span(started_at=datetime(2026, 9, 26))
    with pytest.raises(ValidationError):
        ContextSnapshot(
            snapshot_id="snapshot_1",
            request_index=0,
            total_bytes=-1,
            context_budget_bytes=1,
            message_count=0,
            tool_schema_count=0,
            parts=(),
            by_kind=(),
            truncated=False,
            omitted_entry_count=0,
            omitted_bytes=0,
        )


def test_context_snapshot_contract_enforces_detail_entry_limit() -> None:
    parts = tuple(
        ContextPart(
            kind="system",
            source_ref=f"system:{index}",
            content_hash=f"{index:064x}",
            byte_count=1,
            occurrence_count=1,
            message_count=1,
            schema_count=0,
            truncated=False,
        )
        for index in range(257)
    )
    with pytest.raises(ValidationError):
        ContextSnapshot(
            snapshot_id="snapshot_1",
            request_index=1,
            total_bytes=257,
            context_budget_bytes=1,
            message_count=257,
            tool_schema_count=0,
            parts=parts,
            by_kind=(ContextKindTotal(kind="system", byte_count=257, entry_count=257),),
            truncated=False,
            omitted_entry_count=0,
            omitted_bytes=0,
        )


def test_run_trace_requires_trace_id_to_match_run_id_and_span_trace_ids() -> None:
    with pytest.raises(ValidationError):
        RunTrace(
            run_id="run_1",
            trace_id="different_trace",
            session_id=None,
            started_at=datetime(2026, 9, 26, tzinfo=UTC),
            finished_at=None,
            duration_ms=None,
            status="active",
            spans=(),
            context_snapshots=(),
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
            completeness="complete",
            diagnostic_codes=(),
        )
