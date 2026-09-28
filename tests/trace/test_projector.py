from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vera.contracts.events import EventEnvelope
from vera.trace.projector import TraceProjector

_BASE = datetime(2026, 9, 26, tzinfo=UTC)


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, object] | None = None,
    *,
    seconds: float | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"evt_{sequence}",
        run_id="run_trace",
        sequence=sequence,
        timestamp=_BASE + timedelta(seconds=seconds if seconds is not None else sequence),
        type=event_type,
        payload=payload or {},
    )


def _snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "snapshot_1",
        "request_index": 1,
        "total_bytes": 0,
        "context_budget_bytes": 4096,
        "message_count": 0,
        "tool_schema_count": 0,
        "parts": [],
        "by_kind": [],
        "truncated": False,
        "omitted_entry_count": 0,
        "omitted_bytes": 0,
    }


def test_projects_exact_trace_tree_usage_and_context_snapshot() -> None:
    span_id = "span_llm"
    events = (
        _event(1, "run.started", {"run_id": "run_trace"}, seconds=0),
        _event(
            2,
            "trace.span.started",
            {
                "trace_id": "run_trace",
                "span_id": span_id,
                "parent_span_id": None,
                "kind": "llm",
                "name": "provider attempt",
                "started_at": _BASE.isoformat(),
                "attributes": {"attempt": 1, "provider_type": "deepseek"},
            },
            seconds=0.1,
        ),
        _event(
            3,
            "trace.context.snapshot",
            {"trace_id": "run_trace", "span_id": span_id, "snapshot": _snapshot()},
            seconds=0.2,
        ),
        _event(
            4,
            "model.completed",
            {
                "span_id": span_id,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "total_tokens": 12,
                    "cache_hit_input_tokens": 4,
                    "cache_miss_input_tokens": 6,
                },
            },
            seconds=1,
        ),
        _event(
            5,
            "trace.span.finished",
            {
                "trace_id": "run_trace",
                "span_id": span_id,
                "parent_span_id": None,
                "kind": "llm",
                "name": "provider attempt",
                "started_at": _BASE.isoformat(),
                "finished_at": (_BASE + timedelta(seconds=1)).isoformat(),
                "duration_ms": 900.0,
                "status": "ok",
                "attributes": {"finish_reason": "stop", "total_tokens": 12},
            },
            seconds=1,
        ),
        _event(6, "run.completed", {"state": "completed"}, seconds=2),
    )

    trace = TraceProjector().project("run_trace", events, session_id="session_a")

    assert trace.trace_id == trace.run_id == "run_trace"
    assert trace.session_id == "session_a"
    assert trace.status == "completed"
    assert trace.duration_ms == 2000.0
    assert trace.completeness == "complete", trace.diagnostic_codes
    assert len(trace.spans) == 1
    assert trace.spans[0].span_id == span_id
    assert trace.spans[0].event_ids == ("evt_2", "evt_3", "evt_5")
    assert trace.spans[0].attributes["attempt"] == 1
    assert trace.spans[0].attributes["finish_reason"] == "stop"
    assert trace.context_snapshots[0].snapshot_id == "snapshot_1"
    assert trace.token_usage.status == "complete"
    assert trace.token_usage.total_tokens == 12
    assert trace.token_usage.cache_hit_input_tokens == 4


def test_projects_legacy_events_with_partial_usage_and_unknown_duration() -> None:
    events = (
        _event(1, "run.started", seconds=0),
        _event(2, "model.requested", {"turn": 1, "attempt": 1}, seconds=0.2),
        _event(3, "model.retrying", {"attempt": 1, "code": "provider_timeout"}, seconds=0.5),
        _event(4, "model.requested", {"turn": 1, "attempt": 2}, seconds=0.6),
        _event(
            5,
            "model.completed",
            {"attempt": 2, "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}},
            seconds=1,
        ),
        _event(6, "tool.started", {"name": "read_file", "call_id": "call_1"}, seconds=1.1),
        _event(
            7,
            "tool.completed",
            {"name": "read_file", "call_id": "call_1", "ok": True},
            seconds=1.5,
        ),
        _event(
            8,
            "verification.started",
            {"index": 0, "argv": ["pytest", "-q"]},
            seconds=1.6,
        ),
        _event(
            9,
            "verification.completed",
            {
                "index": 0,
                "status": "passed",
                "exit_code": 0,
                "stdout": "must-not-enter-trace",
                "stderr": "",
            },
            seconds=1.8,
        ),
        _event(10, "run.completed", seconds=2),
    )

    trace = TraceProjector().project("run_trace", events)

    assert [span.kind for span in trace.spans] == ["llm", "llm", "tool", "verification"]
    assert [span.status for span in trace.spans] == ["error", "ok", "ok", "ok"]
    assert all(span.duration_ms is None for span in trace.spans)
    assert trace.retry_count == 1
    assert trace.spans[1].attributes["retry_of_span_id"] == trace.spans[0].span_id
    assert trace.tool_call_count == 1
    assert trace.verification_count == 1
    assert "must-not-enter-trace" not in str(trace.spans)
    assert trace.token_usage.status == "complete"
    assert trace.token_usage.total_tokens == 4
    assert trace.token_usage.cache_hit_input_tokens is None


def test_partial_usage_and_open_spans_remain_explicitly_unknown() -> None:
    events = (
        _event(1, "run.started", seconds=0),
        _event(2, "model.requested", {"turn": 1, "attempt": 1}, seconds=0.1),
        _event(
            3,
            "model.completed",
            {"usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}},
            seconds=1,
        ),
        _event(4, "model.requested", {"turn": 2, "attempt": 1}, seconds=1.1),
        _event(5, "model.completed", {"usage": None}, seconds=2),
        _event(6, "model.requested", {"turn": 3, "attempt": 1}, seconds=2.1),
    )

    trace = TraceProjector().project("run_trace", events)

    assert trace.status == "active"
    assert trace.completeness == "partial"
    assert trace.spans[-1].status == "unknown"
    assert trace.spans[-1].finished_at is None
    assert trace.token_usage.status == "partial"
    assert trace.token_usage.known_token_subtotal == 12
    assert trace.token_usage.usage_unknown_calls == 1
    assert trace.token_usage.total_tokens is None


def test_damaged_and_unknown_trace_events_degrade_locally() -> None:
    events = (
        _event(1, "run.started", seconds=0),
        _event(2, "trace.span.started", {"span_id": "span_bad", "kind": "not-a-kind"}),
        _event(3, "trace.future.event", {"data": "ignored"}),
        _event(
            4,
            "trace.span.started",
            {
                "trace_id": "run_trace",
                "span_id": "span_ok",
                "kind": "tool",
                "name": "read_file",
                "started_at": _BASE.isoformat(),
                "attributes": {"value": float("nan")},
            },
        ),
        _event(
            5,
            "trace.span.finished",
            {
                "trace_id": "run_trace",
                "span_id": "span_ok",
                "kind": "tool",
                "name": "read_file",
                "started_at": _BASE.isoformat(),
                "finished_at": (_BASE - timedelta(seconds=1)).isoformat(),
                "duration_ms": -1,
                "status": "ok",
                "attributes": {},
            },
        ),
        _event(6, "run.failed", seconds=3),
    )

    trace = TraceProjector().project("run_trace", events)

    assert trace.status == "failed"
    assert trace.completeness == "partial"
    assert trace.spans[0].status == "unknown"
    assert trace.spans[0].duration_ms is None
    assert "trace_event_unknown" in trace.diagnostic_codes
    assert "span_attributes_invalid" in trace.diagnostic_codes
    assert "span_time_order_invalid" in trace.diagnostic_codes


def test_duplicate_span_ids_and_zero_usage_are_diagnosed_without_losing_totals() -> None:
    events = (
        _event(1, "run.started", seconds=0),
        _event(
            2,
            "trace.span.started",
            {
                "trace_id": "run_trace",
                "span_id": "span_1",
                "kind": "llm",
                "name": "attempt",
                "started_at": _BASE.isoformat(),
            },
        ),
        _event(
            3,
            "trace.span.started",
            {
                "trace_id": "run_trace",
                "span_id": "span_1",
                "kind": "llm",
                "name": "duplicate",
                "started_at": _BASE.isoformat(),
            },
        ),
        _event(
            4,
            "trace.span.finished",
            {
                "trace_id": "run_trace",
                "span_id": "span_1",
                "kind": "llm",
                "name": "attempt",
                "started_at": _BASE.isoformat(),
                "finished_at": (_BASE + timedelta(seconds=1)).isoformat(),
                "duration_ms": 1000,
                "status": "ok",
            },
        ),
        _event(
            5,
            "model.completed",
            {
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cache_hit_input_tokens": 0,
                    "cache_miss_input_tokens": 0,
                }
            },
        ),
        _event(6, "run.completed", seconds=2),
    )

    trace = TraceProjector().project("run_trace", events)

    assert len(trace.spans) == 1
    assert "span_event_duplicate" in trace.diagnostic_codes
    assert trace.token_usage.status == "complete"
    assert trace.token_usage.total_tokens == 0
    assert trace.token_usage.cache_hit_input_tokens == 0
