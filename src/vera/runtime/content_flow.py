"""Content provenance, project guidance, and conversation seeding flows."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from vera.content.detector import ContentDetection, DetectionDisposition
from vera.content.envelope import (
    ContentEnvelope,
    build_content_envelope,
    render_content_for_model,
    render_project_guidance_for_model,
)
from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.models.base import ModelMessage
from vera.runtime.context import RunContext
from vera.runtime.flow_protocols import ContentFlowHost
from vera.runtime.prompts import COMPACTION_PROMPT, SYSTEM_PROMPT
from vera.runtime.security import (
    MAX_SECURITY_FINDINGS,
    current_security_hash,
    merge_finding,
    security_payload,
)


def record_finding(
    host: ContentFlowHost,
    context: RunContext,
    envelope: ContentEnvelope,
    detection: ContentDetection,
) -> list[EventEnvelope]:
    if context.findings_truncated:
        return []
    merged, added = merge_finding(context.security_findings, envelope, detection)
    if not added:
        return []
    if len(context.security_findings) >= MAX_SECURITY_FINDINGS:
        context.findings_truncated = True
        return [
            host._event(
                context,
                "security.findings_truncated",
                {"limit": MAX_SECURITY_FINDINGS, "dropped": True},
            )
        ]
    context.security_findings = merged
    context.security_context_hash = current_security_hash(merged)
    return [host._event(context, "security.content_flagged", security_payload(envelope, detection))]


def prepare_content(
    host: ContentFlowHost,
    context: RunContext,
    text: str,
    *,
    source_kind: str | None,
    origin: str,
    truncated: bool = False,
) -> tuple[ContentEnvelope, str, list[EventEnvelope]]:
    envelope = build_content_envelope(
        text,
        source_kind=source_kind,
        origin=origin,
        truncated=truncated,
    )
    detection = host.content_detector.assess(envelope, text)
    envelope = envelope.model_copy(update={"risk_labels": detection.risk_labels})
    events: list[EventEnvelope] = []
    if detection.disposition is not DetectionDisposition.CLEAR:
        events.extend(record_finding(host, context, envelope, detection))
    return envelope, render_content_for_model(envelope, text), events


def seed_context(host: ContentFlowHost, context: RunContext) -> Iterator[EventEnvelope]:
    command = context.command
    system = COMPACTION_PROMPT if command.mode == "compact" else SYSTEM_PROMPT
    context.messages.append(ModelMessage(role="system", content=system))
    if command.mode != "compact":
        yield from seed_project_instructions(host, context)
    for message in command.conversation:
        yield from append_conversation_message(host, context, message)
    envelope, rendered, events = prepare_content(
        host,
        context,
        command.goal,
        source_kind="user_goal",
        origin="start_run.goal",
    )
    del envelope
    context.messages.append(ModelMessage(role="user", content=rendered))
    yield from events
    context.context_bytes = sum(len(item.content.encode("utf-8")) for item in context.messages)


def seed_project_instructions(
    host: ContentFlowHost, context: RunContext
) -> Iterator[EventEnvelope]:
    loaded = host.project_instructions.load(context.command.workspace_root)
    context.project_instructions = loaded
    yield host._event(
        context,
        "project.instructions.loaded",
        {
            "guidance_hash": loaded.guidance_hash,
            "sources": [
                {
                    "name": item.name,
                    "priority": item.priority,
                    "content_hash": item.content_hash,
                    "byte_count": item.byte_count,
                }
                for item in loaded.sources
            ],
        },
    )
    if loaded.issues:
        yield host._event(
            context,
            "project.instructions.skipped",
            {
                "issues": [
                    {"name": item.name, "reason_code": item.reason_code} for item in loaded.issues
                ],
            },
        )
    rendered_items: list[tuple[ContentEnvelope, str, int]] = []
    for source in loaded.sources:
        envelope, _rendered, events = prepare_content(
            host,
            context,
            source.content,
            source_kind="project_guidance",
            origin=source.name,
        )
        yield from events
        rendered_items.append((envelope, source.content, source.priority))
    if rendered_items:
        context.messages.append(
            ModelMessage(
                role="user",
                content=render_project_guidance_for_model(rendered_items),
            )
        )


def append_conversation_message(
    host: ContentFlowHost, context: RunContext, message: ConversationMessage
) -> Iterator[EventEnvelope]:
    role: Literal["user", "assistant"]
    if message.role == "summary":
        source_kind, origin, role = "conversation_summary", "conversation.summary", "assistant"
    elif message.role == "assistant":
        source_kind, origin, role = "model_output", "conversation.assistant", "assistant"
    else:
        source_kind, origin, role = "user_goal", "conversation.user", "user"
    _envelope, rendered, events = prepare_content(
        host,
        context,
        message.content,
        source_kind=source_kind,
        origin=origin,
    )
    context.messages.append(ModelMessage(role=role, content=rendered))
    yield from events


__all__ = [
    "append_conversation_message",
    "prepare_content",
    "record_finding",
    "seed_context",
    "seed_project_instructions",
]
