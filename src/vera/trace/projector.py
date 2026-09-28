"""Deterministic, read-only RunTrace projection over append-only Journal events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import TurnCommittedPayload
from vera.contracts.trace import (
    ContextSnapshot,
    RunTrace,
    RunTraceStatus,
    TraceCompleteness,
    TraceSpan,
    TraceSpanKind,
    TraceSpanStatus,
    TraceTokenUsage,
)
from vera.persistence.run_store import RunStore
from vera.persistence.session_store import ConversationSessionStore
from vera.redaction import Redactor

_TERMINAL: dict[str, RunTraceStatus] = {
    "run.completed": "completed",
    "run.failed": "failed",
    "run.cancelled": "cancelled",
}
_TRACE_START = "trace.span.started"
_TRACE_FINISH = "trace.span.finished"


def _text(payload: dict[str, Any], key: str, *, limit: int = 256) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        return None
    return value[:limit]


def _integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
        if number >= 0 and number < float("inf"):
            return number
    return None


def _timestamp(value: object, fallback: datetime) -> datetime:
    if not isinstance(value, str):
        return fallback.astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback.astimezone(UTC)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return fallback.astimezone(UTC)
    return parsed.astimezone(UTC)


def _safe_attributes(value: object, diagnostics: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        candidate = TraceSpan(
            span_id="validation",
            trace_id="validation",
            kind="context",
            name="validation",
            started_at=None,
            finished_at=None,
            duration_ms=None,
            status="unknown",
            attributes=value,
        )
    except (ValidationError, TypeError, ValueError):
        diagnostics.append("span_attributes_invalid")
        return {}
    return dict(candidate.attributes)


class TraceProjector:
    """Project Trace contracts without changing or trusting source Events."""

    def project(
        self,
        run_id: str,
        events: tuple[EventEnvelope, ...],
        *,
        session_id: str | None = None,
    ) -> RunTrace:
        diagnostics: list[str] = []
        ordered = tuple(sorted(events, key=lambda item: item.sequence))
        for event in ordered:
            if event.run_id != run_id:
                diagnostics.append("event_run_id_mismatch")

        started_event = next((event for event in ordered if event.type == "run.started"), None)
        terminal_event = next((event for event in ordered if event.type in _TERMINAL), None)
        if started_event is None:
            started_at = None
            run_status: RunTraceStatus = "unknown"
            diagnostics.append("run_start_missing")
        else:
            started_at = started_event.timestamp.astimezone(UTC)
            if terminal_event is not None:
                run_status = _TERMINAL[terminal_event.type]
            else:
                unresolved_approval = False
                for event in ordered:
                    if event.type == "approval.required":
                        unresolved_approval = True
                    elif event.type in {
                        "approval.resolved",
                        "approval.expired",
                        "approval.invalidated",
                    }:
                        unresolved_approval = False
                run_status = "awaiting_approval" if unresolved_approval else "active"

        finished_at = terminal_event.timestamp.astimezone(UTC) if terminal_event else None
        duration_ms: float | None = None
        if started_at is not None and finished_at is not None:
            elapsed = (finished_at - started_at).total_seconds() * 1000
            if elapsed < 0:
                diagnostics.append("run_time_order_invalid")
            else:
                duration_ms = elapsed

        exact_spans, exact_ids = self._project_exact_spans(run_id, ordered, diagnostics)
        legacy_spans = self._project_legacy_spans(run_id, ordered, exact_ids, diagnostics)
        spans = tuple(sorted((*exact_spans, *legacy_spans), key=self._span_order))

        snapshots: list[ContextSnapshot] = []
        snapshot_indexes: set[int] = set()
        for event in ordered:
            if event.type != "trace.context.snapshot":
                continue
            payload = event.payload
            raw_snapshot = payload.get("snapshot")
            try:
                snapshot = ContextSnapshot.model_validate(raw_snapshot)
            except (ValidationError, TypeError, ValueError):
                diagnostics.append("context_snapshot_invalid")
                continue
            if payload.get("trace_id") != run_id:
                diagnostics.append("context_trace_id_mismatch")
                continue
            if snapshot.request_index in snapshot_indexes:
                diagnostics.append("context_request_index_duplicate")
                continue
            snapshot_indexes.add(snapshot.request_index)
            snapshots.append(snapshot)
        snapshots.sort(key=lambda item: item.request_index)

        usage = self._usage(ordered, diagnostics)
        retry_count = sum(event.type == "model.retrying" for event in ordered)
        if retry_count == 0:
            retry_count = sum("retry_of_span_id" in span.attributes for span in spans)
        tool_count = max(
            sum(event.type == "tool.started" for event in ordered),
            sum(span.kind == "tool" for span in spans),
        )
        verification_count = max(
            sum(event.type == "verification.started" for event in ordered),
            sum(span.kind == "verification" for span in spans),
        )

        if started_event is None:
            completeness: TraceCompleteness = "unknown"
        elif (
            terminal_event is not None
            and not diagnostics
            and all(span.status != "unknown" and span.duration_ms is not None for span in spans)
        ):
            completeness = "complete"
        else:
            completeness = "partial"

        unique_diagnostics = tuple(dict.fromkeys(diagnostics))
        return RunTrace(
            run_id=run_id,
            trace_id=run_id,
            session_id=session_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=run_status,
            spans=spans,
            context_snapshots=tuple(snapshots),
            token_usage=usage,
            retry_count=retry_count,
            tool_call_count=tool_count,
            verification_count=verification_count,
            completeness=completeness,
            diagnostic_codes=unique_diagnostics,
        )

    @staticmethod
    def _span_order(span: TraceSpan) -> tuple[datetime, str]:
        return (span.started_at or datetime.min.replace(tzinfo=UTC), span.span_id)

    def _project_exact_spans(
        self,
        run_id: str,
        events: tuple[EventEnvelope, ...],
        diagnostics: list[str],
    ) -> tuple[tuple[TraceSpan, ...], set[str]]:
        starts: dict[str, tuple[EventEnvelope, dict[str, Any]]] = {}
        finishes: dict[str, tuple[EventEnvelope, dict[str, Any]]] = {}
        context_events: dict[str, list[EventEnvelope]] = {}
        span_ids: set[str] = set()
        for event in events:
            if event.type == "trace.context.snapshot":
                span_id = _text(event.payload, "span_id", limit=128)
                if span_id and event.payload.get("trace_id") == run_id:
                    context_events.setdefault(span_id, []).append(event)
                continue
            if event.type not in {_TRACE_START, _TRACE_FINISH}:
                if event.type.startswith("trace."):
                    diagnostics.append("trace_event_unknown")
                continue
            payload = event.payload
            span_id = _text(payload, "span_id", limit=128)
            if span_id is None:
                diagnostics.append("span_id_missing")
                continue
            if payload.get("trace_id") != run_id:
                diagnostics.append("span_trace_id_mismatch")
                continue
            target = starts if event.type == _TRACE_START else finishes
            if span_id in target:
                diagnostics.append("span_event_duplicate")
                continue
            target[span_id] = (event, payload)

        spans: list[TraceSpan] = []
        for span_id, (start_event, start) in starts.items():
            finish_pair = finishes.get(span_id)
            kind = start.get("kind")
            name = _text(start, "name", limit=160)
            if name is None or kind not in {"llm", "tool", "verification", "context"}:
                diagnostics.append("span_start_invalid")
                continue
            kind = cast(TraceSpanKind, kind)
            start_time = _timestamp(start.get("started_at"), start_event.timestamp)
            start_attributes = _safe_attributes(start.get("attributes", {}), diagnostics)
            parent_span_id = start.get("parent_span_id")
            if not isinstance(parent_span_id, str):
                parent_span_id = None

            if finish_pair is None:
                status: TraceSpanStatus = "unknown"
                finish_time = None
                elapsed_ms = None
                attributes = start_attributes
                event_ids: tuple[str, ...] = tuple(
                    item.event_id
                    for item in sorted(
                        (start_event, *context_events.get(span_id, ())),
                        key=lambda item: item.sequence,
                    )
                )
                diagnostics.append("span_unfinished")
            else:
                finish_event, finish = finish_pair
                finish_kind = finish.get("kind", kind)
                finish_parent = finish.get("parent_span_id", parent_span_id)
                if finish_kind != kind or finish_parent != parent_span_id:
                    diagnostics.append("span_finish_mismatch")
                finish_time = _timestamp(finish.get("finished_at"), finish_event.timestamp)
                elapsed_ms = _number(finish.get("duration_ms"))
                raw_status = finish.get("status")
                if raw_status not in {
                    "ok",
                    "error",
                    "rejected",
                    "cancelled",
                    "interrupted",
                    "unknown",
                }:
                    status = "unknown"
                    diagnostics.append("span_status_invalid")
                else:
                    status = raw_status
                finish_attributes = _safe_attributes(finish.get("attributes", {}), diagnostics)
                attributes = {**start_attributes, **finish_attributes}
                event_ids = tuple(
                    item.event_id
                    for item in sorted(
                        (start_event, *context_events.get(span_id, ()), finish_event),
                        key=lambda item: item.sequence,
                    )
                )
                if finish_event.sequence <= start_event.sequence or finish_time < start_time:
                    diagnostics.append("span_time_order_invalid")
                    status = "unknown"
                    finish_time = None
                    elapsed_ms = None
                elif _number(finish.get("duration_ms")) is None:
                    diagnostics.append("span_duration_invalid")
                    status = "unknown"
                    elapsed_ms = None

            try:
                span = TraceSpan(
                    span_id=span_id,
                    trace_id=run_id,
                    parent_span_id=parent_span_id,
                    kind=kind,
                    name=name,
                    started_at=start_time,
                    finished_at=finish_time,
                    duration_ms=elapsed_ms,
                    status=status,
                    attributes=attributes,
                    event_ids=event_ids,
                )
            except (ValidationError, TypeError, ValueError):
                diagnostics.append("span_invalid")
                try:
                    span = TraceSpan(
                        span_id=span_id,
                        trace_id=run_id,
                        parent_span_id=parent_span_id,
                        kind=kind,
                        name=name,
                        started_at=start_time,
                        finished_at=None,
                        duration_ms=None,
                        status="unknown",
                        attributes={},
                        event_ids=event_ids,
                    )
                except (ValidationError, TypeError, ValueError):
                    continue
            spans.append(span)
            span_ids.add(span_id)

        for _span_id in finishes.keys() - span_ids:
            diagnostics.append("span_finish_without_start")
        return tuple(spans), span_ids

    def _project_legacy_spans(
        self,
        run_id: str,
        events: tuple[EventEnvelope, ...],
        exact_ids: set[str],
        diagnostics: list[str],
    ) -> tuple[TraceSpan, ...]:
        pending_model: dict[int, EventEnvelope] = {}
        pending_tools: dict[str, EventEnvelope] = {}
        pending_verification: dict[int, EventEnvelope] = {}
        spans: list[TraceSpan] = []
        retry_parent: str | None = None
        retry_of_by_start_sequence: dict[int, str] = {}

        def make_span(
            kind: TraceSpanKind,
            name: str,
            start: EventEnvelope,
            finish: EventEnvelope | None,
            *,
            status: TraceSpanStatus,
            attributes: dict[str, Any],
            span_id: str,
        ) -> None:
            if span_id in exact_ids:
                return
            try:
                spans.append(
                    TraceSpan(
                        span_id=span_id,
                        trace_id=run_id,
                        parent_span_id=None,
                        kind=kind,
                        name=name[:160],
                        started_at=start.timestamp,
                        finished_at=finish.timestamp if finish else None,
                        duration_ms=None,
                        status=status,
                        attributes=attributes,
                        event_ids=(start.event_id, finish.event_id)
                        if finish
                        else (start.event_id,),
                    )
                )
            except (ValidationError, TypeError, ValueError):
                diagnostics.append("legacy_span_invalid")

        for event in events:
            payload = event.payload
            if event.type == "model.requested":
                attempt = _integer(payload.get("attempt"))
                span_id = _text(payload, "span_id")
                if attempt is not None and span_id not in exact_ids:
                    pending_model[attempt] = event
                    if retry_parent is not None:
                        retry_of_by_start_sequence[event.sequence] = retry_parent
                        retry_parent = None
            elif event.type in {"model.completed", "model.failed", "model.retrying"}:
                attempt = _integer(payload.get("attempt"))
                span_id = _text(payload, "span_id")
                if attempt is None or attempt not in pending_model:
                    continue
                start = pending_model.pop(attempt)
                synthesized_id = span_id or f"legacy_llm_{start.event_id}"
                status: TraceSpanStatus = "ok" if event.type == "model.completed" else "error"
                attributes: dict[str, Any] = {"attempt": attempt}
                finish_reason = _text(payload, "finish_reason")
                if finish_reason:
                    attributes["finish_reason"] = finish_reason
                error_code = _text(payload, "code") or _text(payload, "reason_code")
                if error_code:
                    attributes["error_code"] = error_code
                retry_of = retry_of_by_start_sequence.get(start.sequence)
                if retry_of is not None:
                    attributes["retry_of_span_id"] = retry_of
                make_span(
                    "llm",
                    "provider attempt",
                    start,
                    event,
                    status=status,
                    attributes=attributes,
                    span_id=synthesized_id,
                )
                if event.type == "model.retrying":
                    retry_parent = synthesized_id
            elif event.type == "tool.started":
                call_id = _text(payload, "call_id")
                if call_id and _text(payload, "span_id") not in exact_ids:
                    pending_tools[call_id] = event
            elif event.type == "tool.completed":
                call_id = _text(payload, "call_id")
                if not call_id or call_id not in pending_tools:
                    continue
                start = pending_tools.pop(call_id)
                ok = payload.get("ok") is True
                status = "ok" if ok else ("rejected" if payload.get("reason_code") else "error")
                attrs: dict[str, Any] = {"tool_name": _text(payload, "name") or "unknown"}
                error = _text(payload, "error_code") or _text(payload, "reason_code")
                if error:
                    attrs["error_code"] = error
                make_span(
                    "tool",
                    attrs["tool_name"],
                    start,
                    event,
                    status=status,
                    attributes=attrs,
                    span_id=_text(payload, "span_id") or f"legacy_tool_{start.event_id}",
                )
            elif event.type == "verification.started":
                index = _integer(payload.get("index"))
                if index is not None and _text(payload, "span_id") not in exact_ids:
                    pending_verification[index] = event
            elif event.type == "verification.completed":
                index = _integer(payload.get("index"))
                if index is None or index not in pending_verification:
                    continue
                start = pending_verification.pop(index)
                status_value = payload.get("status")
                status = (
                    "ok"
                    if status_value == "passed"
                    else ("rejected" if status_value == "rejected" else "error")
                )
                verification_attributes: dict[str, Any] = {"index": index}
                for field in ("exit_code", "reason_code", "artifact_cleanup_status"):
                    value = payload.get(field)
                    if isinstance(value, int | str) and not isinstance(value, bool):
                        verification_attributes[field] = value
                make_span(
                    "verification",
                    "verification command",
                    start,
                    event,
                    status=status,
                    attributes=verification_attributes,
                    span_id=_text(payload, "span_id") or f"legacy_verification_{start.event_id}",
                )

        for attempt, start in pending_model.items():
            make_span(
                "llm",
                "provider attempt",
                start,
                None,
                status="unknown",
                attributes={"attempt": attempt},
                span_id=f"legacy_llm_{start.event_id}",
            )
        for call_id, start in pending_tools.items():
            make_span(
                "tool",
                _text(start.payload, "name") or "unknown",
                start,
                None,
                status="unknown",
                attributes={"tool_call_id": call_id},
                span_id=f"legacy_tool_{start.event_id}",
            )
        for index, start in pending_verification.items():
            make_span(
                "verification",
                "verification command",
                start,
                None,
                status="unknown",
                attributes={"index": index},
                span_id=f"legacy_verification_{start.event_id}",
            )
        return tuple(spans)

    @staticmethod
    def _usage(events: tuple[EventEnvelope, ...], diagnostics: list[str]) -> TraceTokenUsage:
        completed = [event for event in events if event.type == "model.completed"]
        if not completed:
            return TraceTokenUsage(
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
        known: list[tuple[int, int, int, dict[str, Any]]] = []
        unknown_calls = 0
        cache_valid = True
        for event in completed:
            raw = event.payload.get("usage")
            if not isinstance(raw, dict):
                unknown_calls += 1
                continue
            input_tokens = _integer(raw.get("input_tokens"))
            output_tokens = _integer(raw.get("output_tokens"))
            total_tokens = _integer(raw.get("total_tokens"))
            if input_tokens is None or output_tokens is None or total_tokens is None:
                unknown_calls += 1
                continue
            known.append((input_tokens, output_tokens, total_tokens, raw))
            hit = _integer(raw.get("cache_hit_input_tokens"))
            miss = _integer(raw.get("cache_miss_input_tokens"))
            if hit is None or miss is None or hit + miss != input_tokens:
                cache_valid = False
        if not known:
            return TraceTokenUsage(
                status="unavailable",
                calls=len(completed),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cache_hit_input_tokens=None,
                cache_miss_input_tokens=None,
                known_token_subtotal=None,
                usage_unknown_calls=len(completed),
            )
        subtotal = sum(item[2] for item in known)
        if unknown_calls:
            return TraceTokenUsage(
                status="partial",
                calls=len(completed),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cache_hit_input_tokens=None,
                cache_miss_input_tokens=None,
                known_token_subtotal=subtotal,
                usage_unknown_calls=unknown_calls,
            )
        return TraceTokenUsage(
            status="complete",
            calls=len(completed),
            input_tokens=sum(item[0] for item in known),
            output_tokens=sum(item[1] for item in known),
            total_tokens=subtotal,
            cache_hit_input_tokens=(
                sum(_integer(item[3].get("cache_hit_input_tokens")) or 0 for item in known)
                if cache_valid
                else None
            ),
            cache_miss_input_tokens=(
                sum(_integer(item[3].get("cache_miss_input_tokens")) or 0 for item in known)
                if cache_valid
                else None
            ),
            known_token_subtotal=subtotal,
            usage_unknown_calls=0,
        )


def trace_snapshot(
    store: RunStore,
    run_id: str,
    *,
    session_id: str | None = None,
    installation_id: str | None = None,
) -> RunTrace:
    events = store.read_events(run_id)
    diagnostics: list[str] = []
    resolved_session = None
    started = next((event for event in events if event.type == "run.started"), None)
    workspace_value = started.payload.get("workspace_root") if started is not None else None
    if isinstance(workspace_value, str) and workspace_value:
        workspace = Path(workspace_value).expanduser().resolve()
        if installation_id is not None:
            session_store = ConversationSessionStore(store.state_dir, installation_id, Redactor([]))
            try:
                summaries = session_store.list_for_workspace(workspace)
            except (OSError, ValueError):
                summaries = ()
                diagnostics.append("session_scan_failed")
            candidate_ids = [item.session_id for item in summaries]
            if session_id is not None and session_id not in candidate_ids:
                diagnostics.append("session_workspace_mismatch")
            else:
                for summary in summaries:
                    if session_id is not None and summary.session_id != session_id:
                        continue
                    if not summary.recoverable:
                        diagnostics.append("session_journal_corrupt")
                        continue
                    try:
                        loaded = session_store.load(summary.session_id, workspace)
                    except (OSError, ValueError):
                        diagnostics.append("session_journal_corrupt")
                        continue
                    committed_run_ids = {
                        record.payload.turn.run_id
                        for record in loaded.records
                        if record.type == "turn.committed"
                        and isinstance(record.payload, TurnCommittedPayload)
                        and record.payload.turn.run_id is not None
                    }
                    if run_id in committed_run_ids:
                        resolved_session = summary.session_id
                        break
                if session_id is not None and resolved_session is None:
                    diagnostics.append("session_run_not_committed")
    elif session_id is not None:
        diagnostics.append("session_workspace_unavailable")

    trace = TraceProjector().project(run_id, events, session_id=resolved_session)
    if not diagnostics:
        return trace
    return trace.model_copy(
        update={"diagnostic_codes": tuple(dict.fromkeys((*trace.diagnostic_codes, *diagnostics)))}
    )
