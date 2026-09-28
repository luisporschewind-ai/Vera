"""Versioned, local-only contracts for Run Trace projections."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from vera.contracts import ContractModel, JsonValue

TraceSpanKind = Literal["llm", "tool", "verification", "context"]
TraceSpanStatus = Literal["ok", "error", "rejected", "cancelled", "interrupted", "unknown"]
ContextKind = Literal[
    "system",
    "project_guidance",
    "skill",
    "conversation",
    "user_input",
    "assistant_tool_call",
    "tool_result",
    "compaction_summary",
    "tool_schema",
    "other",
]
RunTraceStatus = Literal[
    "active", "awaiting_approval", "completed", "failed", "cancelled", "unknown"
]
TraceCompleteness = Literal["complete", "partial", "unknown"]
TraceUsageStatus = Literal["complete", "partial", "unavailable"]

NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeFloat = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
OptionalTokenCount = Annotated[int | None, Field(strict=True, ge=0)]

MAX_TRACE_ATTRIBUTES = 32
MAX_TRACE_ATTRIBUTE_BYTES = 8_192
MAX_CONTEXT_PARTS = 256
MAX_CONTEXT_SNAPSHOT_BYTES = 65_536
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _validate_attributes(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if len(value) > MAX_TRACE_ATTRIBUTES:
        raise ValueError("trace attributes exceed the entry limit")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("trace attributes must be finite JSON values") from exc
    if len(encoded) > MAX_TRACE_ATTRIBUTE_BYTES:
        raise ValueError("trace attributes exceed the byte limit")
    return value


class ContextPart(ContractModel):
    kind: ContextKind
    source_ref: str = Field(min_length=1, max_length=160)
    content_hash: str = Field(pattern=_SHA256_RE.pattern)
    byte_count: NonNegativeInt
    occurrence_count: PositiveInt
    message_count: NonNegativeInt
    schema_count: NonNegativeInt
    truncated: bool = False

    @model_validator(mode="after")
    def counts_match_occurrences(self) -> ContextPart:
        if self.message_count + self.schema_count != self.occurrence_count:
            raise ValueError("message and schema counts must match occurrences")
        return self


class ContextKindTotal(ContractModel):
    kind: ContextKind
    byte_count: NonNegativeInt
    entry_count: NonNegativeInt


class ContextSnapshot(ContractModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    request_index: PositiveInt
    total_bytes: NonNegativeInt
    context_budget_bytes: NonNegativeInt
    message_count: NonNegativeInt
    tool_schema_count: NonNegativeInt
    parts: tuple[ContextPart, ...]
    by_kind: tuple[ContextKindTotal, ...]
    truncated: bool
    omitted_entry_count: NonNegativeInt
    omitted_bytes: NonNegativeInt

    @model_validator(mode="after")
    def details_match_totals(self) -> ContextSnapshot:
        if len(self.parts) > MAX_CONTEXT_PARTS:
            raise ValueError("context snapshot exceeds the part limit")
        if len({item.kind for item in self.by_kind}) != len(self.by_kind):
            raise ValueError("context kind totals must be unique")
        if sum(item.byte_count for item in self.by_kind) != self.total_bytes:
            raise ValueError("context kind byte totals must match total_bytes")
        if sum(item.byte_count for item in self.parts) + self.omitted_bytes != self.total_bytes:
            raise ValueError("retained and omitted part bytes must match total_bytes")
        if sum(item.occurrence_count for item in self.parts) + self.omitted_entry_count != sum(
            item.entry_count for item in self.by_kind
        ):
            raise ValueError("retained and omitted entries must match context totals")
        if self.message_count + self.tool_schema_count != sum(
            item.entry_count for item in self.by_kind
        ):
            raise ValueError("message and schema counts must match context entries")
        has_truncated_part = any(item.truncated for item in self.parts)
        if self.truncated != (
            self.omitted_entry_count > 0 or self.omitted_bytes > 0 or has_truncated_part
        ):
            raise ValueError("truncated must reflect omitted context details")
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_CONTEXT_SNAPSHOT_BYTES:
            raise ValueError("context snapshot exceeds the byte limit")
        return self


class TraceSpan(ContractModel):
    span_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    parent_span_id: str | None = Field(default=None, max_length=128)
    kind: TraceSpanKind
    name: str = Field(min_length=1, max_length=160)
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: NonNegativeFloat | None
    status: TraceSpanStatus
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    event_ids: tuple[str, ...] = ()

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None

    @field_validator("attributes")
    @classmethod
    def attributes_are_bounded_json(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _validate_attributes(value)


class TraceTokenUsage(ContractModel):
    status: TraceUsageStatus
    calls: NonNegativeInt
    input_tokens: OptionalTokenCount
    output_tokens: OptionalTokenCount
    total_tokens: OptionalTokenCount
    cache_hit_input_tokens: OptionalTokenCount
    cache_miss_input_tokens: OptionalTokenCount
    known_token_subtotal: OptionalTokenCount
    usage_unknown_calls: NonNegativeInt

    @model_validator(mode="after")
    def status_matches_known_usage(self) -> TraceTokenUsage:
        totals = (self.input_tokens, self.output_tokens, self.total_tokens)
        if self.status == "complete" and (
            self.calls == 0 or any(item is None for item in totals) or self.usage_unknown_calls
        ):
            raise ValueError("complete usage requires known totals for every call")
        if self.status == "partial" and (
            self.known_token_subtotal is None or self.usage_unknown_calls == 0
        ):
            raise ValueError("partial usage requires a known subtotal and unknown calls")
        if self.status == "unavailable" and any(item is not None for item in totals):
            raise ValueError("unavailable usage cannot expose aggregate totals")
        return self


class RunTrace(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: NonNegativeFloat | None
    status: RunTraceStatus
    spans: tuple[TraceSpan, ...]
    context_snapshots: tuple[ContextSnapshot, ...]
    token_usage: TraceTokenUsage
    retry_count: NonNegativeInt
    tool_call_count: NonNegativeInt
    verification_count: NonNegativeInt
    completeness: TraceCompleteness
    diagnostic_codes: tuple[str, ...]

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None

    @model_validator(mode="after")
    def trace_ids_are_consistent(self) -> RunTrace:
        if self.trace_id != self.run_id:
            raise ValueError("trace_id must equal run_id")
        if any(span.trace_id != self.trace_id for span in self.spans):
            raise ValueError("all spans must belong to the run trace")
        if len({span.span_id for span in self.spans}) != len(self.spans):
            raise ValueError("span IDs must be unique within a RunTrace")
        if any(
            left.request_index >= right.request_index
            for left, right in zip(self.context_snapshots, self.context_snapshots[1:], strict=False)
        ):
            raise ValueError("context snapshots must be ordered by request_index")
        return self


__all__ = [
    "ContextKind",
    "ContextKindTotal",
    "ContextPart",
    "ContextSnapshot",
    "RunTrace",
    "RunTraceStatus",
    "TraceCompleteness",
    "TraceSpan",
    "TraceSpanKind",
    "TraceSpanStatus",
    "TraceTokenUsage",
    "TraceUsageStatus",
]
