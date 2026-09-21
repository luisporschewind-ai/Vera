"""Session event handlers for the timeline projector."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import ValidationError

from vera.contracts.events import EventEnvelope
from vera.presentation.diagnostics_copy import format_config_body, format_doctor_body
from vera.presentation.event_copy import event_summary, event_title
from vera.presentation.mutations import TimelineMutation
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.status_panel import format_status_panel
from vera.presentation.timeline import BlockKind, BlockStatus
from vera.project_instructions import format_instruction_status
from vera.session.models import SessionStatus

if TYPE_CHECKING:
    from vera.presentation.projector import TimelineProjector


def session_status(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    try:
        status = SessionStatus.model_validate(event.payload)
    except ValidationError:
        return host._session_message(event)
    body = format_status_panel(status)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:status",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=event_title(event.type),
        body=sanitize_terminal_text(body),
        status=BlockStatus.SUCCEEDED,
    )


def session_doctor(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:status",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=event_title(event.type),
        body=sanitize_terminal_text(format_doctor_body(event.payload)),
        status=BlockStatus.SUCCEEDED,
    )


def session_config(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:status",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=event_title(event.type),
        body=sanitize_terminal_text(format_config_body(event.payload)),
        status=BlockStatus.SUCCEEDED,
    )


def session_message(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    if event.payload.get("clear_display"):
        return ()
    text = event.payload.get("text")
    if isinstance(text, str) and text.strip():
        body = text.strip()
        lines = body.splitlines()
        if len(lines) == 1:
            title = event_title(event.type)
        else:
            first = lines[0]
            title = first if len(first) <= 40 else first[:37] + "..."
    else:
        title = event_title(event.type)
        body = event_summary(event.payload)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:status",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=title,
        body=body,
        status=BlockStatus.SUCCEEDED,
    )


def persistence_warning(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    advice = event.payload.get("advice")
    if isinstance(advice, str) and advice.strip():
        body = advice.strip()
    else:
        body = event_summary(event.payload)
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:error",
        run_id=event.run_id,
        kind=BlockKind.ERROR,
        title=event_title(event.type),
        body=sanitize_terminal_text(body),
        status=BlockStatus.FAILED,
    )


def instruction_status(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    text = event.payload.get("text")
    if isinstance(text, str) and text.strip():
        body = text.strip()
    else:
        body = format_instruction_status(dict(event.payload))
    return host._append(
        block_id=f"{event.run_id}:{event.sequence}:status",
        run_id=event.run_id,
        kind=BlockKind.STATUS,
        title=event_title(event.type),
        body=sanitize_terminal_text(body),
        status=BlockStatus.SUCCEEDED,
    )


def session_loaded(host: TimelineProjector, event: EventEnvelope) -> tuple[TimelineMutation, ...]:
    from vera.session.startup import HISTORY_DISPLAY_LIMIT

    items = event.payload.get("items") or []
    if not isinstance(items, list):
        items = []
    bounded = items[-HISTORY_DISPLAY_LIMIT:]
    mutations: list[TimelineMutation] = []
    for index, item in enumerate(bounded):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", ""))
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        kind = BlockKind.USER if role == "user" else BlockKind.ASSISTANT
        title = "你" if role == "user" else "Vera" if role == "assistant" else "摘要"
        stamp = item.get("timestamp")
        occurred_at = stamp if isinstance(stamp, datetime) else None
        mutations.extend(
            host._append(
                block_id=f"{event.run_id}:{event.sequence}:hist:{index}",
                run_id=event.run_id,
                kind=kind,
                title=title,
                body=sanitize_terminal_text(content),
                status=BlockStatus.SUCCEEDED,
                occurred_at=occurred_at,
            )
        )
    return tuple(mutations)
