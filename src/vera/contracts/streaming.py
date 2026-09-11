"""Transient stream frames for in-process UI updates."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self, TypeGuard

from pydantic import Field, model_validator

from vera.contracts import ContractModel, JsonValue
from vera.contracts.events import EventEnvelope


class StreamFrameType(StrEnum):
    ASSISTANT_DELTA = "assistant.delta"


class StreamFrame(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    stream_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    type: StreamFrameType
    payload: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_delta(self) -> Self:
        text = self.payload.get("text")
        if self.type is StreamFrameType.ASSISTANT_DELTA and (not isinstance(text, str) or not text):
            raise ValueError("assistant.delta requires non-empty text")
        return self


type RuntimeOutput = EventEnvelope | StreamFrame


def is_transient(output: RuntimeOutput) -> TypeGuard[StreamFrame]:
    return isinstance(output, StreamFrame)
