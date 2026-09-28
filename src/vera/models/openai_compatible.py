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
    ModelIdentity,
    ModelRequest,
    ModelToolCall,
    ModelTurn,
)
from vera.models.capabilities import ModelCapabilities
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.leaked_markup import LeakedMarkupFilter
from vera.models.provider_usage import parse_provider_usage
from vera.models.streaming import (
    ModelStreamAccumulator,
    ModelStreamCompleted,
    ModelStreamItem,
    ModelTextDelta,
)
from vera.models.tool_arguments import decode_tool_arguments
from vera.runtime.context import normalize_tool_transcript


def _get(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _provider_attr(value: object, *names: str) -> Any:
    """Read declared fields or provider extras the OpenAI SDK may hide."""

    if value is None:
        return None
    sources: list[object] = [value]
    extra = _get(value, "model_extra") or _get(value, "__pydantic_extra__")
    if isinstance(extra, dict):
        sources.append(extra)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            payload = dump()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            sources.append(payload)
    for source in sources:
        for name in names:
            found = _get(source, name)
            if isinstance(found, str) and found:
                return found
            if isinstance(found, dict):
                nested = found.get("content") or found.get("text")
                if isinstance(nested, str) and nested:
                    return nested
    return None


def coerce_assistant_text(value: object) -> str | None:
    """Normalize provider content that may be a string, list of parts, or object."""

    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            part = coerce_assistant_text(item)
            if part:
                parts.append(part)
        return "".join(parts) or None
    if isinstance(value, dict):
        for key in ("text", "content"):
            found = value.get(key)
            if isinstance(found, str) and found:
                return found
        return None
    nested = _get(value, "text")
    if nested is None:
        nested = _get(value, "content")
    if nested is not None and nested is not value:
        return coerce_assistant_text(nested)
    return None


class OpenAICompatibleAdapter:
    def __init__(
        self,
        provider: ProviderConfig,
        client: Any | None = None,
        *,
        api_key: str | None = None,
        profile_name: str | None = None,
        provider_type: str = "openai-compatible",
    ) -> None:
        self.provider = provider
        caps = provider.capabilities
        if caps.reasoning == "unavailable":
            caps = caps.model_copy(update={"reasoning": "provider_default"})
        self._capabilities = caps
        self._identity = ModelIdentity(
            provider_type=provider_type,
            profile_name=profile_name,
            model_name=provider.model,
        )
        self.client: Any = client or OpenAI(
            api_key=api_key if api_key is not None else os.environ.get(provider.api_key_env),
            base_url=str(provider.base_url),
            timeout=120.0,
            max_retries=0,
        )

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    @property
    def identity(self) -> ModelIdentity:
        return self._identity

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
        last_calls: dict[str, str] = {}
        for message in normalize_tool_transcript(list(request.messages)):
            content: object = message.content
            if message.tool_calls and not message.content.strip():
                content = None
            item: dict[str, object] = {
                "role": message.role,
                "content": content,
            }
            if message.role == "assistant" and message.tool_calls:
                last_calls = {
                    call.call_id: call.name for call in message.tool_calls if call.call_id
                }
            if message.role == "tool":
                if not message.tool_call_id:
                    continue
                item["tool_call_id"] = message.tool_call_id
                name = last_calls.get(message.tool_call_id)
                if name:
                    item["name"] = name
            elif message.tool_call_id is not None:
                item["tool_call_id"] = message.tool_call_id
            if message.reasoning_content:
                item["reasoning_content"] = message.reasoning_content
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
            }
            kwargs[self.provider.output_token_parameter] = request.max_output_tokens
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
        visible = LeakedMarkupFilter()
        try:
            kwargs: dict[str, object] = {
                "model": self.provider.model,
                "messages": self._messages(request),
                "stream": True,
            }
            kwargs[self.provider.output_token_parameter] = request.max_output_tokens
            if self.provider.stream_usage_mode == "include_usage":
                kwargs["stream_options"] = {"include_usage": True}
            if request.tools:
                kwargs["tools"] = self._tools(request)
            response = self.client.chat.completions.create(**kwargs)
            finish_reason = "stop"
            for chunk in response:
                usage_value = _get(chunk, "usage")
                if usage_value is not None:
                    accumulator.usage = parse_provider_usage(usage_value)
                choice = (_get(chunk, "choices") or [None])[0]
                if choice is None:
                    continue
                delta = _get(choice, "delta") or {}
                text = coerce_assistant_text(_get(delta, "content"))
                if text:
                    accumulator.push_text(text)
                    shown = visible.push(text)
                    if shown:
                        yield ModelTextDelta(text=shown)
                reasoning = (
                    _provider_attr(delta, "reasoning_content", "reasoning")
                    or _provider_attr(choice, "reasoning_content", "reasoning")
                    or _provider_attr(_get(choice, "message"), "reasoning_content", "reasoning")
                )
                if isinstance(reasoning, str) and reasoning:
                    accumulator.push_reasoning(reasoning)
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
                request_id = _get(chunk, "_request_id") or _get(chunk, "id")
                if request_id:
                    accumulator.provider_request_id = str(request_id)
            tail = visible.flush()
            if tail:
                yield ModelTextDelta(text=tail)
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
            name = str(_get(function, "name", "") or "")
            if not name:
                raise ModelProviderError(
                    ModelErrorCode.INVALID_RESPONSE, "provider returned incomplete tool call"
                )
            arguments, parse_error = decode_tool_arguments(_get(function, "arguments", "{}"))
            calls.append(
                ModelToolCall(
                    call_id=str(_get(raw_call, "id", "")),
                    name=name,
                    arguments=arguments,
                    parse_error=parse_error,
                )
            )
        usage_value = _get(response, "usage")
        usage = None
        if usage_value is not None:
            usage = parse_provider_usage(usage_value)
        request_id = _get(response, "_request_id") or _get(response, "id")
        reasoning = _provider_attr(message, "reasoning_content", "reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            reasoning = None
        return ModelTurn(
            assistant_text=coerce_assistant_text(_get(message, "content")),
            reasoning_content=reasoning,
            tool_calls=tuple(calls),
            finish_reason=finish_reason,
            usage=usage,
            provider_request_id=str(request_id) if request_id else None,
        )
