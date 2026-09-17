"""Immutable timeline block view models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BlockKind(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    LOG = "log"
    DIFF = "diff"
    APPROVAL = "approval"
    VERIFICATION = "verification"
    ERROR = "error"
    STATUS = "status"


class BlockStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TimelineBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    kind: BlockKind
    title: str
    body: str = ""
    status: BlockStatus = BlockStatus.PENDING
    expanded: bool = False
    user_overridden: bool = False
    incomplete: bool = False
    truncated: bool = False
    ref_id: str | None = None
    occurred_at: datetime | None = None
    created_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _alias_occurrence(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        stamp = data.get("occurred_at")
        if stamp is None:
            stamp = data.get("created_at")
        if stamp is None:
            return data
        aliased = dict(data)
        aliased["occurred_at"] = stamp
        aliased["created_at"] = stamp
        return aliased


def format_block_clock(value: datetime | None) -> str:
    """Local 12-hour `h:mm AM` / `h:mm PM`. Empty when unknown."""

    from vera.presentation.timeline_time import format_timeline_clock

    return format_timeline_clock(value)
