"""Stable provider-neutral model protocol."""

from collections import deque
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from vera.contracts import JsonValue
from vera.tools.definitions import ToolDefinition


class ModelToolCall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    name: str
    arguments: dict[str, JsonValue]


class ModelMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolDefinition, ...] = ()
    max_output_tokens: int = Field(ge=1)


class ModelUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ModelTurn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assistant_text: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    finish_reason: str
    usage: ModelUsage | None = None
    provider_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ModelAdapter(Protocol):
    def complete(self, request: ModelRequest) -> ModelTurn: ...


class FakeModelAdapter:
    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = deque(turns)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        if not self._turns:
            raise AssertionError("FakeModelAdapter has no scripted turn")
        return self._turns.popleft()
