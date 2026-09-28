"""Immutable timeline mutation contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.presentation.timeline import TimelineBlock


class AppendBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["append"] = "append"
    block: TimelineBlock


class UpdateBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["update"] = "update"
    block: TimelineBlock


class FocusBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["focus"] = "focus"
    block_id: str


TimelineMutation = Annotated[
    AppendBlock | UpdateBlock | FocusBlock,
    Field(discriminator="type"),
]


__all__ = ["AppendBlock", "FocusBlock", "TimelineMutation", "UpdateBlock"]
