"""Immutable timeline block view models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
