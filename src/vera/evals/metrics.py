"""Extract evaluation latency and usage without inventing missing numbers."""

from __future__ import annotations

from dataclasses import dataclass

from vera.contracts.events import EventEnvelope
from vera.evals.contracts import EvalMetrics
from vera.models.base import ModelUsage

_TERMINAL = frozenset({"run.completed", "run.failed", "run.cancelled", "recovery.abandoned"})
_MAX_TOKENS = 1_000_000_000


@dataclass(frozen=True)
class ExtractedMetrics:
    metrics: EvalMetrics
    reason_codes: tuple[str, ...] = ()


class MetricsExtractor:
    def extract(
        self, events: tuple[EventEnvelope, ...], wall_duration_seconds: float | None
    ) -> ExtractedMetrics:
        reasons: list[str] = []
        started = next((event.timestamp for event in events if event.type == "run.started"), None)
        terminal = next(
            (event.timestamp for event in reversed(events) if event.type in _TERMINAL),
            None,
        )
        event_duration: float | None = None
        if started is not None and terminal is not None:
            delta = (terminal - started).total_seconds()
            if delta < 0:
                reasons.append("invalid_event_time")
            else:
                event_duration = delta
        usage = _aggregate_usage(events)
        return ExtractedMetrics(
            metrics=EvalMetrics(
                wall_duration_seconds=wall_duration_seconds,
                event_duration_seconds=event_duration,
                usage=usage,
            ),
            reason_codes=tuple(reasons),
        )


def _aggregate_usage(events: tuple[EventEnvelope, ...]) -> ModelUsage | None:
    completed = [event for event in events if event.type == "model.completed"]
    if not completed:
        return None
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for event in completed:
        payload = event.payload.get("usage")
        if not isinstance(payload, dict):
            return None
        for field in totals:
            value = payload.get(field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                or value > _MAX_TOKENS
            ):
                return None
            totals[field] += value
            if totals[field] > _MAX_TOKENS:
                return None
    return ModelUsage(
        input_tokens=totals["input_tokens"],
        output_tokens=totals["output_tokens"],
        total_tokens=totals["total_tokens"],
    )
