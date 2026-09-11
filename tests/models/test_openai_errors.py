"""Broader OpenAI-compatible adapter coverage."""

from types import SimpleNamespace

import pytest

from vera.config import ProviderConfig
from vera.models.base import ModelMessage, ModelRequest
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.tools.definitions import ToolDefinition


class FakeOpenAIClient:
    def __init__(self, response: object | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object) -> object:
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


def provider() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://api.example.test/v1",  # type: ignore[arg-type]
        model="test-model",
        api_key_env="TEST_API_KEY",
    )


def request_with_tools() -> ModelRequest:
    return ModelRequest(
        messages=(
            ModelMessage(role="user", content="inspect"),
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=(),
            ),
            ModelMessage(role="tool", content="ok", tool_call_id="call_1"),
        ),
        tools=(ToolDefinition(name="read_file", description="read", input_schema={}),),
        max_output_tokens=100,
    )


def test_adapter_rejects_empty_choices() -> None:
    client = FakeOpenAIClient(SimpleNamespace(choices=[], usage=None))
    with pytest.raises(ModelProviderError) as caught:
        OpenAICompatibleAdapter(provider(), client=client).complete(request_with_tools())
    assert caught.value.code is ModelErrorCode.INVALID_RESPONSE


def test_adapter_rejects_unknown_finish_reason() -> None:
    choice = SimpleNamespace(
        message=SimpleNamespace(content="x", tool_calls=None),
        finish_reason="nope",
    )
    response = SimpleNamespace(choices=[choice], usage=None, id="req_1")
    with pytest.raises(ModelProviderError) as caught:
        OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(
            request_with_tools()
        )
    assert caught.value.code is ModelErrorCode.INVALID_RESPONSE


def test_adapter_maps_generic_exception() -> None:
    adapter = OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(exc=RuntimeError("x")))
    with pytest.raises(ModelProviderError) as caught:
        adapter.complete(request_with_tools())
    assert caught.value.code is ModelErrorCode.SERVICE


def test_adapter_round_trips_text_and_request_id() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="hello", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        id="req_text",
    )
    turn = OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(
        ModelRequest(messages=(ModelMessage(role="user", content="hi"),), max_output_tokens=16)
    )
    assert turn.assistant_text == "hello"
    assert turn.provider_request_id == "req_text"
    assert turn.usage is not None
