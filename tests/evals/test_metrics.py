from datetime import UTC, datetime, timedelta

from vera.contracts.events import EventEnvelope
from vera.evals.metrics import MetricsExtractor
from vera.models.base import ModelUsage


def _event(
    seq: int,
    event_type: str,
    payload: dict | None = None,
    *,
    offset: float = 0,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{seq}",
        run_id="run-1",
        sequence=seq,
        timestamp=datetime(2026, 9, 12, tzinfo=UTC) + timedelta(seconds=offset),
        type=event_type,
        payload=payload or {},
    )


def model_completed(usage: dict | None, seq: int = 2, offset: float = 0.1) -> EventEnvelope:
    return _event(seq, "model.completed", {"usage": usage}, offset=offset)


def timestamped_completed_run() -> tuple[EventEnvelope, ...]:
    return (
        _event(1, "run.started", offset=0.0),
        model_completed(
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            seq=2,
            offset=0.1,
        ),
        _event(3, "run.completed", offset=0.4),
    )


def test_usage_is_null_when_any_model_event_lacks_usage() -> None:
    metrics = MetricsExtractor().extract(
        events=(
            model_completed({"total_tokens": 5, "input_tokens": 2, "output_tokens": 3}, seq=1),
            model_completed(None, seq=2),
        ),
        wall_duration_seconds=0.25,
    )
    assert metrics.metrics.usage is None
    assert metrics.metrics.wall_duration_seconds == 0.25


def test_event_duration_uses_first_started_and_last_terminal() -> None:
    extracted = MetricsExtractor().extract(timestamped_completed_run(), 1.0)
    assert extracted.metrics.event_duration_seconds == 0.4
    assert extracted.metrics.usage == ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)


def test_missing_token_field_nulls_usage() -> None:
    extracted = MetricsExtractor().extract(
        (model_completed({"input_tokens": 1, "output_tokens": None, "total_tokens": 1}),),
        0.1,
    )
    assert extracted.metrics.usage is None


def test_negative_duration_is_invalid() -> None:
    events = (
        _event(1, "run.started", offset=1.0),
        _event(2, "run.completed", offset=0.2),
    )
    extracted = MetricsExtractor().extract(events, 0.5)
    assert extracted.metrics.event_duration_seconds is None
    assert "invalid_event_time" in extracted.reason_codes


def test_no_terminal_event_leaves_event_duration_none() -> None:
    extracted = MetricsExtractor().extract((_event(1, "run.started"),), 0.2)
    assert extracted.metrics.event_duration_seconds is None
