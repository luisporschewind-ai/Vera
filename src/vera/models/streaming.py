"""Normalized model stream items and accumulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vera.models.base import ModelToolCall, ModelTurn, ModelUsage
from vera.models.errors import ModelErrorCode, ModelProviderError


@dataclass(frozen=True)
class ModelTextDelta:
    text: str


@dataclass(frozen=True)
class ModelStreamCompleted:
    turn: ModelTurn


type ModelStreamItem = ModelTextDelta | ModelStreamCompleted


@dataclass
class _ToolDraft:
    call_id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class ModelStreamAccumulator:
    text_parts: list[str] = field(default_factory=list)
    tools: dict[int, _ToolDraft] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    provider_request_id: str | None = None

    def push_text(self, text: str) -> None:
        if text:
            self.text_parts.append(text)

    def push_tool_delta(
        self,
        index: int,
        *,
        call_id: str | None = None,
        name: str | None = None,
        arguments: str | None = None,
    ) -> None:
        draft = self.tools.setdefault(index, _ToolDraft())
        if call_id:
            draft.call_id = call_id
        if name:
            draft.name += name
        if arguments:
            draft.arguments += arguments

    def finish(
        self,
        *,
        finish_reason: str,
        usage: ModelUsage | None = None,
        provider_request_id: str | None = None,
    ) -> ModelTurn:
        import json

        calls: list[ModelToolCall] = []
        for index in sorted(self.tools):
            draft = self.tools[index]
            try:
                arguments: Any = json.loads(draft.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE,
                    "provider returned invalid tool arguments",
                ) from exc
            if not isinstance(arguments, dict):
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE,
                    "tool arguments must be an object",
                )
            if not draft.name:
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE,
                    "provider returned incomplete tool call",
                )
            calls.append(
                ModelToolCall(
                    call_id=draft.call_id or f"call_{index}",
                    name=draft.name,
                    arguments=arguments,
                )
            )
        text = "".join(self.text_parts) or None
        return ModelTurn(
            assistant_text=text,
            tool_calls=tuple(calls),
            finish_reason=finish_reason,
            usage=usage or self.usage,
            provider_request_id=provider_request_id or self.provider_request_id,
        )
