from types import SimpleNamespace

import pytest

from vera.config import ProviderConfig
from vera.models.base import ModelMessage, ModelRequest, ModelToolCall
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.tools.definitions import ToolDefinition


class FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self.response


def provider() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://api.example.test/v1",
        model="test-model",
        api_key_env="TEST_API_KEY",
    )


def request() -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(role="user", content="inspect"),),
        tools=(ToolDefinition(name="read_file", description="read", input_schema={}),),
        max_output_tokens=100,
    )


def test_openai_adapter_defaults_reasoning_to_provider_default() -> None:
    adapter = OpenAICompatibleAdapter(provider(), client=object())
    assert adapter.capabilities.reasoning == "provider_default"
    assert provider().capabilities.reasoning == "unavailable"


def test_completion_uses_selected_output_token_parameter() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=[]), finish_reason="stop"
            )
        ],
        usage=None,
    )
    client = FakeOpenAIClient(response)
    selected = provider().model_copy(update={"output_token_parameter": "max_completion_tokens"})
    OpenAICompatibleAdapter(selected, client=client).complete(request())
    assert client.kwargs["max_completion_tokens"] == 100
    assert "max_tokens" not in client.kwargs


def test_adapter_normalizes_provider_tool_call() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="read_file", arguments='{"path":"README.md"}'
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    turn = OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(
        request()
    )
    assert turn.tool_calls == (
        ModelToolCall(call_id="call_1", name="read_file", arguments={"path": "README.md"}),
    )
    assert turn.usage is not None and turn.usage.total_tokens == 5


def test_adapter_keeps_invalid_tool_json_as_parse_error() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(name="read_file", arguments="oops"),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=None,
    )
    turn = OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(
        request()
    )
    assert turn.tool_calls == (
        ModelToolCall(
            call_id="call_1",
            name="read_file",
            arguments={},
            parse_error="invalid_tool_arguments",
        ),
    )


def test_adapter_rejects_incomplete_tool_name() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(name="", arguments="{}"),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=None,
    )
    with pytest.raises(ModelProviderError) as caught:
        OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(request())
    assert caught.value.code is ModelErrorCode.INVALID_RESPONSE
