"""Deterministic event-trace helper used by the monolith refactor tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vera.contracts.events import EventEnvelope


def normalize_event_trace(events: list[EventEnvelope]) -> tuple[dict[str, Any], ...]:
    """Remove run-local identifiers and timestamps without mutating events."""

    return tuple(
        {
            "sequence": event.sequence,
            "type": event.type,
            "payload": event.payload,
        }
        for event in events
    )


def test_normalize_event_trace_ignores_run_local_identity_and_timestamp() -> None:
    first = EventEnvelope(
        event_id="event-a",
        run_id="run-a",
        sequence=1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        type="run.started",
        payload={"state": "running"},
    )
    second = first.model_copy(
        update={
            "event_id": "event-b",
            "run_id": "run-b",
            "timestamp": datetime(2026, 2, 1, tzinfo=UTC),
        }
    )

    assert normalize_event_trace([first]) == normalize_event_trace([second])
    assert first.event_id == "event-a"
    assert first.run_id == "run-a"
