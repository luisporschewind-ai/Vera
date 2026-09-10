from types import SimpleNamespace

import pytest

from vera.config import ProviderConfig
from vera.models.base import ModelMessage, ModelRequest, ModelToolCall
from vera.models.openai_compatible import ModelAdapterError, OpenAICompatibleAdapter
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
    turn = OpenAICompatibleAdapter(
        provider(), client=FakeOpenAIClient(response)
    ).complete(request())
    assert turn.tool_calls == (
        ModelToolCall(call_id="call_1", name="read_file", arguments={"path": "README.md"}),
    )
    assert turn.usage is not None and turn.usage.total_tokens == 5


def test_adapter_rejects_invalid_tool_json() -> None:
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
    with pytest.raises(ModelAdapterError):
        OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(request())
