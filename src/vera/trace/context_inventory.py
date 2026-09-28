"""Bounded, body-free inventory of the exact messages and schemas in a request."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel

from vera.contracts.trace import (
    MAX_CONTEXT_PARTS,
    MAX_CONTEXT_SNAPSHOT_BYTES,
    ContextKind,
    ContextKindTotal,
    ContextPart,
    ContextSnapshot,
)
from vera.models.base import ModelMessage, ModelRequest

if TYPE_CHECKING:
    from vera.runtime.context import RunContext


@dataclass
class _PartAccumulator:
    kind: ContextKind
    source_ref: str
    content_hash: str
    byte_count: int = 0
    occurrence_count: int = 0
    message_count: int = 0
    schema_count: int = 0
    truncated: bool = False

    def contract(self) -> ContextPart:
        return ContextPart(
            kind=self.kind,
            source_ref=self.source_ref,
            content_hash=self.content_hash,
            byte_count=self.byte_count,
            occurrence_count=self.occurrence_count,
            message_count=self.message_count,
            schema_count=self.schema_count,
            truncated=self.truncated,
        )


def _canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decode_object(content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _project_guidance_matches(payload: dict[str, Any], context: RunContext) -> bool:
    instruction_set = getattr(context, "project_instructions", None)
    expected = getattr(instruction_set, "sources", None)
    sources = payload.get("sources")
    if not isinstance(expected, tuple) or not isinstance(sources, list):
        return False
    if len(expected) != len(sources):
        return False
    for source, candidate in zip(expected, sources, strict=True):
        if not isinstance(candidate, dict):
            return False
        if (
            candidate.get("name") != source.name
            or candidate.get("content_hash") != source.content_hash
            or candidate.get("byte_count") != source.byte_count
            or candidate.get("priority") != source.priority
        ):
            return False
    return bool(expected)


def _skill_matches(payload: dict[str, Any], context: RunContext) -> bool:
    parts = getattr(context, "skill_context", ())
    origin = payload.get("origin")
    digest = payload.get("content_hash")
    if not isinstance(parts, tuple) or not isinstance(origin, str) or not isinstance(digest, str):
        return False
    return any(
        getattr(getattr(part, "envelope", None), "origin", None) == origin
        and getattr(getattr(part, "envelope", None), "content_hash", None) == digest
        for part in parts
    )


def _conversation_matches(
    payload: dict[str, Any], context: RunContext, *, expected_origin: str
) -> bool:
    command = getattr(context, "command", None)
    messages = getattr(command, "conversation", ())
    digest = payload.get("content_hash")
    role_by_origin = {
        "conversation.user": "user",
        "conversation.assistant": "assistant",
        "conversation.summary": "summary",
        "conversation.compacted": "summary",
    }
    expected_role = role_by_origin.get(expected_origin)
    if expected_role is None or not isinstance(digest, str):
        return False
    return any(
        message.role == expected_role and _hash_text(message.content) == digest
        for message in messages
    )


def _message_kind(message: ModelMessage, context: RunContext) -> tuple[ContextKind, str, bool]:
    if message.role == "system":
        return "system", "system", False
    if message.role == "tool":
        payload = _decode_object(message.content)
        truncated = payload.get("truncated") is True if payload is not None else False
        return "tool_result", "tool_result", truncated
    if message.role == "assistant" and message.tool_calls:
        return "assistant_tool_call", "assistant_tool_call", False

    payload = _decode_object(message.content)
    if payload is not None:
        source_kind = payload.get("source_kind")
        origin = payload.get("origin")
        if source_kind == "project_guidance" and _project_guidance_matches(payload, context):
            return "project_guidance", "project_guidance", False
        if source_kind == "skill_content" and _skill_matches(payload, context):
            return "skill", "skill_snapshot", payload.get("truncated") is True
        if source_kind == "user_goal" and origin == "start_run.goal":
            command = getattr(context, "command", None)
            goal = getattr(command, "goal", None)
            if isinstance(goal, str) and payload.get("content_hash") == _hash_text(goal):
                return "user_input", "run_goal", payload.get("truncated") is True
        if source_kind in {"user_goal", "model_output", "conversation_summary"}:
            if isinstance(origin, str) and _conversation_matches(
                payload, context, expected_origin=origin
            ):
                if source_kind == "conversation_summary":
                    return (
                        "compaction_summary",
                        "compaction_summary",
                        payload.get("truncated") is True,
                    )
                return (
                    "conversation",
                    f"conversation:{origin.rsplit('.', 1)[-1]}",
                    (payload.get("truncated") is True),
                )
            if source_kind == "conversation_summary" and origin in {
                "conversation.summary",
                "conversation.compacted",
            }:
                return "compaction_summary", "compaction_summary", payload.get("truncated") is True

    if message.role == "assistant":
        return "conversation", "conversation:assistant", False
    return "other", f"other:{message.role}", False


def _bounded_source_ref(value: str) -> str:
    return value[:160]


class ContextInventory:
    """Build a bounded snapshot using request bytes and in-memory provenance only."""

    @classmethod
    def build(
        cls,
        request: ModelRequest,
        context: RunContext,
        *,
        request_index: int,
        context_budget_bytes: int,
    ) -> ContextSnapshot:
        accumulators: dict[tuple[str, str, str], _PartAccumulator] = {}
        kind_totals: dict[ContextKind, list[int]] = {}
        total_bytes = 0

        entries: list[tuple[object, ContextKind, str, bool, bool]] = []
        for message in request.messages:
            kind, source_ref, truncated = _message_kind(message, context)
            entries.append((message, kind, source_ref, truncated, True))
        for tool in request.tools:
            entries.append(
                (tool, "tool_schema", _bounded_source_ref(f"tool_schema:{tool.name}"), False, False)
            )

        for value, kind, source_ref, truncated, is_message in entries:
            encoded = _canonical_bytes(value)
            byte_count = len(encoded)
            content_hash = hashlib.sha256(encoded).hexdigest()
            total_bytes += byte_count
            totals = kind_totals.setdefault(kind, [0, 0])
            totals[0] += byte_count
            totals[1] += 1

            key = (kind, source_ref, content_hash)
            aggregate = accumulators.get(key)
            if aggregate is None:
                aggregate = _PartAccumulator(kind, source_ref, content_hash)
                accumulators[key] = aggregate
            aggregate.byte_count += byte_count
            aggregate.occurrence_count += 1
            aggregate.message_count += int(is_message)
            aggregate.schema_count += int(not is_message)
            aggregate.truncated = aggregate.truncated or truncated

        all_parts = [item.contract() for item in accumulators.values()]
        kind_summaries = tuple(
            ContextKindTotal(kind=kind, byte_count=values[0], entry_count=values[1])
            for kind, values in kind_totals.items()
        )
        snapshot_id = f"snapshot_{uuid4().hex}"
        max_part_count = min(MAX_CONTEXT_PARTS, len(all_parts))

        for retained_count in range(max_part_count, -1, -1):
            retained = tuple(all_parts[:retained_count])
            omitted = all_parts[retained_count:]
            omitted_entry_count = sum(item.occurrence_count for item in omitted)
            omitted_bytes = sum(item.byte_count for item in omitted)
            snapshot_values: dict[str, Any] = {
                "snapshot_id": snapshot_id,
                "request_index": request_index,
                "total_bytes": total_bytes,
                "context_budget_bytes": context_budget_bytes,
                "message_count": len(request.messages),
                "tool_schema_count": len(request.tools),
                "parts": tuple(item.model_dump(mode="json") for item in retained),
                "by_kind": tuple(item.model_dump(mode="json") for item in kind_summaries),
                "truncated": bool(
                    omitted_entry_count or omitted_bytes or any(item.truncated for item in retained)
                ),
                "omitted_entry_count": omitted_entry_count,
                "omitted_bytes": omitted_bytes,
            }
            if len(_canonical_bytes(snapshot_values)) <= MAX_CONTEXT_SNAPSHOT_BYTES:
                return ContextSnapshot.model_validate(snapshot_values)

        raise ValueError("context snapshot summary exceeds the byte limit")
