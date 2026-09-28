from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.trace import ContextSnapshot
from vera.persistence.journal import EventJournal
from vera.redaction import Redactor
from vera.trace.recorder import TraceRecorder


class _Clock:
    def __init__(self) -> None:
        self.values = iter(
            (
                datetime(2026, 9, 26, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 9, 26, 1, 0, 0, 500000, tzinfo=UTC),
                datetime(2026, 9, 26, 1, 0, 0, 750000, tzinfo=UTC),
                datetime(2026, 9, 26, 1, 0, 2, tzinfo=UTC),
            )
        )

    def __call__(self) -> datetime:
        return next(self.values)


def _journal(tmp_path: Path) -> EventJournal:
    return EventJournal(tmp_path, run_id="run_trace", redactor=Redactor())


def _snapshot() -> ContextSnapshot:
    return ContextSnapshot(
        snapshot_id="snapshot_1",
        request_index=1,
        total_bytes=0,
        context_budget_bytes=4096,
        message_count=0,
        tool_schema_count=0,
        parts=(),
        by_kind=(),
        truncated=False,
        omitted_entry_count=0,
        omitted_bytes=0,
    )


def test_recorder_appends_ordered_span_and_context_events(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    monotonic = iter((10.0, 11.0, 11.25, 12.25))
    recorder = TraceRecorder(journal, monotonic=lambda: next(monotonic), clock=_Clock())

    parent = recorder.start_span("llm", "provider attempt", attributes={"attempt": 1})
    child = recorder.start_span("context", "request snapshot", parent_span_id=parent.span_id)
    recorder.record_context(child, _snapshot())
    recorder.finish_span(child, "ok")
    finish = recorder.finish_span(parent, "ok", attributes={"retry_count": 0, "success": True})

    events = journal.read_all()
    assert [event.type for event in events] == [
        "trace.span.started",
        "trace.span.started",
        "trace.context.snapshot",
        "trace.span.finished",
        "trace.span.finished",
    ]
    assert events[0].payload == {
        "trace_id": "run_trace",
        "span_id": parent.span_id,
        "parent_span_id": None,
        "kind": "llm",
        "name": "provider attempt",
        "started_at": "2026-09-26T01:00:00Z",
        "attributes": {"attempt": 1},
    }
    assert events[1].payload["parent_span_id"] == parent.span_id
    assert events[2].payload["snapshot"]["snapshot_id"] == "snapshot_1"
    assert events[2].payload["span_id"] == child.span_id
    assert events[3].payload["duration_ms"] == 250.0
    assert events[4].payload["duration_ms"] == 2250.0
    assert events[3].payload["finished_at"] == "2026-09-26T01:00:00.750000Z"
    assert events[4].payload["finished_at"] == "2026-09-26T01:00:02Z"
    assert finish.sequence == 5

    reopened = EventJournal(tmp_path, run_id="run_trace", redactor=Redactor())
    assert [event.payload for event in reopened.read_all()] == [event.payload for event in events]


def test_recorder_rejects_duplicate_finish_without_appending(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    monotonic = iter((3.0, 4.0))
    recorder = TraceRecorder(journal, monotonic=lambda: next(monotonic), clock=_Clock())
    span = recorder.start_span("tool", "read_file")
    recorder.finish_span(span, "ok")

    with pytest.raises(ValueError, match="already finished"):
        recorder.finish_span(span, "ok")
    assert [event.type for event in journal.read_all()] == [
        "trace.span.started",
        "trace.span.finished",
    ]


def test_recorder_rejects_negative_duration_without_success_event(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    monotonic = iter((5.0, 4.0))
    recorder = TraceRecorder(journal, monotonic=lambda: next(monotonic), clock=_Clock())
    span = recorder.start_span("verification", "tests")

    with pytest.raises(ValueError, match="monotonic"):
        recorder.finish_span(span, "ok")
    assert [event.type for event in journal.read_all()] == ["trace.span.started"]


@pytest.mark.parametrize(
    "attributes",
    [
        {"bad": object()},
        {"ratio": float("nan")},
        {"x" * 8193: "x"},
    ],
)
def test_recorder_rejects_invalid_attributes_before_writing(
    tmp_path: Path, attributes: dict[str, object]
) -> None:
    journal = _journal(tmp_path)
    recorder = TraceRecorder(journal)

    with pytest.raises((TypeError, ValueError)):
        recorder.start_span("llm", "provider attempt", attributes=attributes)
    assert journal.read_all() == ()


def test_recorder_delegates_redaction_to_journal(tmp_path: Path) -> None:
    journal = EventJournal(
        tmp_path,
        run_id="run_trace",
        redactor=Redactor(["private-provider-secret"]),
    )
    recorder = TraceRecorder(journal)
    span = recorder.start_span(
        "llm", "provider attempt", attributes={"detail": "private-provider-secret"}
    )

    payload = json.loads(journal.path.read_text(encoding="utf-8").splitlines()[0])["payload"]
    assert payload["attributes"]["detail"] == "[REDACTED]"
    assert "private-provider-secret" not in journal.path.read_text(encoding="utf-8")
    assert span.trace_id == "run_trace"
