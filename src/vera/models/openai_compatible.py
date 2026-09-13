"""OpenAI-compatible protocol adapter; provider objects stay in this module."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from vera.config import ProviderConfig
from vera.models.base import (
    ModelRequest,
    ModelToolCall,
    ModelTurn,
    ModelUsage,
)
from vera.models.capabilities import ModelCapabilities
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.streaming import (
    ModelStreamAccumulator,
    ModelStreamCompleted,
    ModelStreamItem,
    ModelTextDelta,
)


def _get(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class OpenAICompatibleAdapter:
    def __init__(self, provider: ProviderConfig, client: Any | None = None) -> None:
        self.provider = provider
        self._capabilities = provider.capabilities
        self.client: Any = client or OpenAI(
            api_key=os.environ.get(provider.api_key_env),
            base_url=str(provider.base_url),
            timeout=120.0,
            max_retries=0,
        )

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

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

    def _map_exception(self, exc: Exception) -> ModelProviderError:
        if isinstance(exc, AuthenticationError):
            return ModelProviderError(
                ModelErrorCode.AUTHENTICATION,
                "provider authentication failed",
                status_code=getattr(exc, "status_code", 401),
            )
        if isinstance(exc, APITimeoutError):
            return ModelProviderError(ModelErrorCode.TIMEOUT, "provider request timed out")
        if isinstance(exc, RateLimitError):
            return ModelProviderError(
                ModelErrorCode.RATE_LIMITED,
                "provider rate limited",
                status_code=getattr(exc, "status_code", 429),
                retry_after_seconds=self._retry_after(exc),
            )
        if isinstance(exc, APIConnectionError):
            return ModelProviderError(ModelErrorCode.NETWORK, "provider network error")
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            server_side = status is not None and status >= 500
            return ModelProviderError(
                ModelErrorCode.SERVICE if server_side else ModelErrorCode.REQUEST_INVALID,
                "provider service error" if server_side else "provider rejected the request",
                status_code=status,
                retry_after_seconds=self._retry_after(exc),
                detail=self._status_detail(exc),
            )
        return ModelProviderError(ModelErrorCode.SERVICE, "provider request failed")

    @staticmethod
    def _status_detail(exc: Exception, *, limit: int = 200) -> str | None:
        """Keep the provider's own reason; a generic label leaves 4xx undiagnosable."""

        message: object = None
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
            elif isinstance(error, str):
                message = error
            if message is None:
                message = body.get("message")
        if not isinstance(message, str) or not message:
            message = getattr(exc, "message", None)
        if not isinstance(message, str) or not message:
            return None
        return " ".join(message.split())[:limit]

    @staticmethod
    def _retry_after(exc: Exception) -> float | None:
        headers = getattr(exc, "headers", None) or {}
        value = None
        if isinstance(headers, dict):
            value = headers.get("retry-after") or headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def complete(self, request: ModelRequest) -> ModelTurn:
        if self.capabilities.streaming:
            items = tuple(self.stream(request))
            completed = next(
                (item for item in reversed(items) if isinstance(item, ModelStreamCompleted)),
                None,
            )
            if completed is None:
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE, "provider stream missing completion"
                )
            return completed.turn
        try:
            kwargs: dict[str, object] = {
                "model": self.provider.model,
                "messages": self._messages(request),
                "max_tokens": request.max_output_tokens,
            }
            if request.tools:
                kwargs["tools"] = self._tools(request)
            response = self.client.chat.completions.create(**kwargs)
        except ModelProviderError:
            raise
        except Exception as exc:
            raise self._map_exception(exc) from exc
        return self._turn_from_response(response)

    def stream(self, request: ModelRequest) -> Iterator[ModelStreamItem]:
        if not self.capabilities.streaming:
            yield ModelStreamCompleted(turn=self.complete(request))
            return
        accumulator = ModelStreamAccumulator()
        try:
            kwargs: dict[str, object] = {
                "model": self.provider.model,
                "messages": self._messages(request),
                "max_tokens": request.max_output_tokens,
                "stream": True,
            }
            if request.tools:
                kwargs["tools"] = self._tools(request)
            response = self.client.chat.completions.create(**kwargs)
            finish_reason = "stop"
            for chunk in response:
                choice = (_get(chunk, "choices") or [None])[0]
                if choice is None:
                    continue
                delta = _get(choice, "delta") or {}
                text = _get(delta, "content")
                if isinstance(text, str) and text:
                    accumulator.push_text(text)
                    yield ModelTextDelta(text=text)
                for raw_call in _get(delta, "tool_calls") or []:
                    index = int(_get(raw_call, "index", 0) or 0)
                    function = _get(raw_call, "function") or {}
                    accumulator.push_tool_delta(
                        index,
                        call_id=_get(raw_call, "id"),
                        name=_get(function, "name"),
                        arguments=_get(function, "arguments"),
                    )
                reason = _get(choice, "finish_reason")
                if reason:
                    finish_reason = reason
                usage_value = _get(chunk, "usage")
                if usage_value is not None:
                    accumulator.usage = ModelUsage(
                        input_tokens=_get(usage_value, "prompt_tokens"),
                        output_tokens=_get(usage_value, "completion_tokens"),
                        total_tokens=_get(usage_value, "total_tokens"),
                    )
                request_id = _get(chunk, "_request_id") or _get(chunk, "id")
                if request_id:
                    accumulator.provider_request_id = str(request_id)
            turn = accumulator.finish(finish_reason=finish_reason)
            yield ModelStreamCompleted(turn=turn)
        except ModelProviderError:
            raise
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def _turn_from_response(self, response: object) -> ModelTurn:
        choices = _get(response, "choices", [])
        if not choices:
            raise ModelProviderError(
                ModelErrorCode.INVALID_RESPONSE, "provider returned no choices"
            )
        choice = choices[0]
        finish_reason = _get(choice, "finish_reason")
        if finish_reason not in {"stop", "tool_calls", "length", "content_filter", "function_call"}:
            raise ModelProviderError(
                ModelErrorCode.INVALID_RESPONSE, f"unknown finish reason: {finish_reason}"
            )
        message = _get(choice, "message")
        calls: list[ModelToolCall] = []
        for raw_call in _get(message, "tool_calls", []) or []:
            function = _get(raw_call, "function")
            try:
                arguments = json.loads(_get(function, "arguments", "{}"))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE, "provider returned invalid tool arguments"
                ) from exc
            if not isinstance(arguments, dict):
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE, "tool arguments must be an object"
                )
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
        request_id = _get(response, "_request_id") or _get(response, "id")
        return ModelTurn(
            assistant_text=_get(message, "content"),
            tool_calls=tuple(calls),
            finish_reason=finish_reason,
            usage=usage,
            provider_request_id=str(request_id) if request_id else None,
        )
