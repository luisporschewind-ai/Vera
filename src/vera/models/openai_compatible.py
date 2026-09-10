"""OpenAI-compatible protocol adapter; provider objects stay in this module."""

import json
import os
from typing import Any

from openai import OpenAI

from vera.config import ProviderConfig
from vera.models.base import (
    ModelRequest,
    ModelToolCall,
    ModelTurn,
    ModelUsage,
)


class ModelAdapterError(RuntimeError):
    """Raised when a provider response cannot become a Vera model turn."""


def _get(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class OpenAICompatibleAdapter:
    def __init__(self, provider: ProviderConfig, client: Any | None = None) -> None:
        self.provider = provider
        self.client: Any = client or OpenAI(
            api_key=os.environ.get(provider.api_key_env),
            base_url=str(provider.base_url),
            timeout=120.0,
            max_retries=0,
        )

    @staticmethod
    def _tools(request: ModelRequest) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in request.tools
        ]

    @staticmethod
    def _messages(request: ModelRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for message in request.messages:
            item: dict[str, object] = {
                "role": message.role,
                "content": message.content,
            }
            if message.tool_call_id is not None:
                item["tool_call_id"] = message.tool_call_id
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.arguments, ensure_ascii=False, separators=(",", ":")
                            ),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(item)
        return messages

    def complete(self, request: ModelRequest) -> ModelTurn:
        try:
            kwargs: dict[str, object] = {
                "model": self.provider.model,
                "messages": self._messages(request),
                "max_tokens": request.max_output_tokens,
            }
            if request.tools:
                kwargs["tools"] = self._tools(request)
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ModelAdapterError("provider request failed") from exc
        choices = _get(response, "choices", [])
        if not choices:
            raise ModelAdapterError("provider returned no choices")
        choice = choices[0]
        finish_reason = _get(choice, "finish_reason")
        if finish_reason not in {"stop", "tool_calls", "length", "content_filter", "function_call"}:
            raise ModelAdapterError(f"unknown finish reason: {finish_reason}")
        message = _get(choice, "message")
        calls: list[ModelToolCall] = []
        for raw_call in _get(message, "tool_calls", []) or []:
            function = _get(raw_call, "function")
            try:
                arguments = json.loads(_get(function, "arguments", "{}"))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ModelAdapterError("provider returned invalid tool arguments") from exc
            if not isinstance(arguments, dict):
                raise ModelAdapterError("tool arguments must be an object")
            calls.append(
                ModelToolCall(
                    call_id=str(_get(raw_call, "id", "")),
                    name=str(_get(function, "name", "")),
                    arguments=arguments,
                )
            )
        usage_value = _get(response, "usage")
        usage = None
        if usage_value is not None:
            usage = ModelUsage(
                input_tokens=_get(usage_value, "prompt_tokens"),
                output_tokens=_get(usage_value, "completion_tokens"),
                total_tokens=_get(usage_value, "total_tokens"),
            )
        return ModelTurn(
            assistant_text=_get(message, "content"),
            tool_calls=tuple(calls),
            finish_reason=finish_reason,
            usage=usage,
        )
