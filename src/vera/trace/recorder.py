"""Append-only recorder for bounded, body-free Trace facts."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from vera.contracts import JsonValue
from vera.contracts.events import EventEnvelope
from vera.contracts.trace import (
    ContextSnapshot,
    TraceSpan,
    TraceSpanKind,
    TraceSpanStatus,
)
from vera.persistence.journal import EventJournal


@dataclass(frozen=True)
class SpanHandle:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    kind: TraceSpanKind
    name: str
    started_at: datetime
    monotonic_started: float


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Trace clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


class TraceRecorder:
    """Record Trace lifecycle events in the Run's existing EventJournal."""

    def __init__(
        self,
        journal: EventJournal,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._journal = journal
        self._monotonic = monotonic
        self._clock = clock
        self._active: dict[str, SpanHandle] = {}
        self._finished: set[str] = set()

    def start_span(
        self,
        kind: TraceSpanKind,
        name: str,
        *,
        parent_span_id: str | None = None,
        attributes: dict[str, JsonValue] | None = None,
    ) -> SpanHandle:
        started_at = _utc(self._clock())
        monotonic_started = self._monotonic()
        if not math.isfinite(monotonic_started):
            raise ValueError("monotonic clock must return a finite value")
        span_id = f"span_{uuid4().hex}"
        safe_attributes = dict(attributes or {})
        # Reuse the public contract's finite-JSON and size validation before any write.
        TraceSpan(
            span_id=span_id,
            trace_id=self._journal.run_id,
            parent_span_id=parent_span_id,
            kind=kind,
            name=name,
            started_at=started_at,
            finished_at=None,
            duration_ms=None,
            status="unknown",
            attributes=safe_attributes,
            event_ids=(),
        )
        handle = SpanHandle(
            span_id=span_id,
            trace_id=self._journal.run_id,
            parent_span_id=parent_span_id,
            kind=kind,
            name=name,
            started_at=started_at,
            monotonic_started=monotonic_started,
        )
        self._journal.append(
            "trace.span.started",
            {
                "trace_id": handle.trace_id,
                "span_id": handle.span_id,
                "parent_span_id": handle.parent_span_id,
                "kind": handle.kind,
                "name": handle.name,
                "started_at": _timestamp(handle.started_at),
                "attributes": safe_attributes,
            },
        )
        self._active[handle.span_id] = handle
        return handle

    def finish_span(
        self,
        handle: SpanHandle,
        status: TraceSpanStatus,
        *,
        attributes: dict[str, JsonValue] | None = None,
        duration_ms: float | None = None,
    ) -> EventEnvelope:
        if handle.span_id in self._finished:
            raise ValueError("span is already finished")
        if self._active.get(handle.span_id) != handle or handle.trace_id != self._journal.run_id:
            raise ValueError("span handle is not active in this recorder")

        safe_attributes = dict(attributes or {})
        if duration_ms is None:
            duration = self._monotonic() - handle.monotonic_started
            if not math.isfinite(duration) or duration < 0:
                raise ValueError("monotonic duration must be finite and nonnegative")
            duration_ms = duration * 1000
        elif not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("duration_ms must be finite and nonnegative")
        finished_at = _utc(self._clock())
        span = TraceSpan(
            span_id=handle.span_id,
            trace_id=handle.trace_id,
            parent_span_id=handle.parent_span_id,
            kind=handle.kind,
            name=handle.name,
            started_at=handle.started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=status,
            attributes=safe_attributes,
            event_ids=(),
        )
        event = self._journal.append(
            "trace.span.finished",
            {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "kind": span.kind,
                "name": span.name,
                "started_at": _timestamp(handle.started_at),
                "finished_at": _timestamp(finished_at),
                "duration_ms": duration_ms,
                "status": status,
                "attributes": safe_attributes,
            },
        )
        self._active.pop(handle.span_id)
        self._finished.add(handle.span_id)
        return event

    def record_context(self, handle: SpanHandle, snapshot: ContextSnapshot) -> EventEnvelope:
        if self._active.get(handle.span_id) != handle or handle.trace_id != self._journal.run_id:
            raise ValueError("span handle is not active in this recorder")
        return self._journal.append(
            "trace.context.snapshot",
            {
                "trace_id": handle.trace_id,
                "span_id": handle.span_id,
                "snapshot": snapshot.model_dump(mode="json"),
            },
        )
