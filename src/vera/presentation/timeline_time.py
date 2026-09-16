"""Authoritative timeline clocks. Widgets never invent a redraw time."""

from __future__ import annotations

import re
from datetime import UTC, datetime, tzinfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vera.presentation.timeline import BlockKind, TimelineBlock

_DECORATIVE = re.compile(r"^[\s\-–—_=*·•▪▸▼►◄|│┃╭╮╯╰┌┐┘└]+$")


def format_timeline_clock(
    value: datetime | None,
    *,
    tz: tzinfo | None = None,
) -> str:
    """Local 24-hour `HH:mm`. Empty when the instant is unknown."""

    if value is None:
        return ""
    instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    local = instant.astimezone(tz) if tz is not None else instant.astimezone()
    return local.strftime("%H:%M")


def block_occurred_at(block: TimelineBlock) -> datetime | None:
    return block.occurred_at if block.occurred_at is not None else block.created_at


def is_decorative_text(text: str) -> bool:
    stripped = text.strip()
    return not stripped or _DECORATIVE.fullmatch(stripped) is not None


def should_omit_timeline_block(
    kind: BlockKind,
    title: str,
    body: str,
    *,
    previous: TimelineBlock | None = None,
) -> bool:
    from vera.presentation.timeline import BlockKind as Kinds

    stripped = body.strip()
    if kind in {Kinds.USER, Kinds.ASSISTANT} and not stripped:
        return True
    if (
        kind in {Kinds.STATUS, Kinds.LOG}
        and is_decorative_text(stripped)
        and is_decorative_text(title)
    ):
        return True
    return (
        kind is Kinds.STATUS
        and previous is not None
        and previous.kind is Kinds.STATUS
        and previous.title == title.strip()
        and previous.body.strip() == stripped
    )
