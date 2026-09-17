"""Broader OpenAI-compatible adapter coverage."""

from types import SimpleNamespace

import pytest

from vera.config import ProviderConfig
from vera.models.base import ModelMessage, ModelRequest, ModelToolCall
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.tools.definitions import ToolDefinition


class FakeOpenAIClient:
    def __init__(self, response: object | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.kwargs: dict[str, object] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
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


def test_adapter_reads_reasoning_content_from_provider_extras() -> None:
    class _ExtraOnly:
        content = ""
        tool_calls = None
        model_extra = {"reasoning_content": "藏在 extras 里"}

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=_ExtraOnly(), finish_reason="stop")],
        usage=None,
        id="req_extra",
    )
    turn = OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(
        ModelRequest(messages=(ModelMessage(role="user", content="hi"),), max_output_tokens=16)
    )
    assert turn.reasoning_content == "藏在 extras 里"


def test_adapter_reads_reasoning_content_from_complete_response() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=None,
                    reasoning_content="先思考再回答",
                ),
                finish_reason="stop",
            )
        ],
        usage=None,
        id="req_think",
    )
    turn = OpenAICompatibleAdapter(provider(), client=FakeOpenAIClient(response)).complete(
        ModelRequest(messages=(ModelMessage(role="user", content="hi"),), max_output_tokens=16)
    )
    assert turn.reasoning_content == "先思考再回答"


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


def test_adapter_omits_unpaired_tool_messages_and_nulls_empty_tool_content() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
        id="req_tools",
    )
    client = FakeOpenAIClient(response)
    OpenAICompatibleAdapter(provider(), client=client).complete(
        ModelRequest(
            messages=(
                ModelMessage(role="system", content="sys"),
                ModelMessage(role="tool", content="dropped"),
                ModelMessage(role="user", content="list"),
                ModelMessage(
                    role="assistant",
                    content="",
                    tool_calls=(
                        ModelToolCall(
                            call_id="call_1",
                            name="list_directory",
                            arguments={"path": "."},
                        ),
                    ),
                ),
                ModelMessage(role="tool", content="ok", tool_call_id="call_1"),
            ),
            max_output_tokens=16,
        )
    )
    sent = client.kwargs["messages"]
    assert isinstance(sent, list)
    assert sent[0] == {"role": "system", "content": "sys"}
    assert sent[1]["role"] == "user"
    assert sent[2]["role"] == "assistant"
    assert sent[2]["content"] is None
    assert sent[2]["tool_calls"][0]["id"] == "call_1"
    assert sent[3] == {
        "role": "tool",
        "content": "ok",
        "tool_call_id": "call_1",
        "name": "list_directory",
    }
    assert all(item.get("role") != "tool" or item.get("tool_call_id") for item in sent)


def test_adapter_echoes_reasoning_content_on_follow_up() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None, reasoning_content=None),
                finish_reason="stop",
            )
        ],
        usage=None,
        id="req_reason",
    )
    client = FakeOpenAIClient(response)
    OpenAICompatibleAdapter(provider(), client=client).complete(
        ModelRequest(
            messages=(
                ModelMessage(role="user", content="list"),
                ModelMessage(
                    role="assistant",
                    content="",
                    reasoning_content="需要先列出目录",
                    tool_calls=(
                        ModelToolCall(
                            call_id="call_1",
                            name="list_directory",
                            arguments={"path": "."},
                        ),
                    ),
                ),
                ModelMessage(role="tool", content="ok", tool_call_id="call_1"),
            ),
            max_output_tokens=16,
        )
    )
    sent = client.kwargs["messages"]
    assert isinstance(sent, list)
    assistant = next(item for item in sent if item["role"] == "assistant")
    assert assistant["reasoning_content"] == "需要先列出目录"
    assert assistant["content"] is None
    for index, item in enumerate(sent):
        if item.get("role") != "tool":
            continue
        previous = sent[index - 1]
        assert previous.get("role") in {"assistant", "tool"}
        if previous.get("role") == "assistant":
            assert previous.get("tool_calls")


def test_adapter_echoes_intact_parallel_tool_round() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None, reasoning_content=None),
                finish_reason="stop",
            )
        ],
        usage=None,
        id="req_parallel",
    )
    client = FakeOpenAIClient(response)
    calls = tuple(
        ModelToolCall(
            call_id=f"call_{index}",
            name="read_file",
            arguments={"path": f"{index}.swift"},
        )
        for index in range(10)
    )
    OpenAICompatibleAdapter(provider(), client=client).complete(
        ModelRequest(
            messages=(
                ModelMessage(role="user", content="analyze"),
                ModelMessage(
                    role="assistant",
                    content="",
                    reasoning_content="需要先读这些文件",
                    tool_calls=calls,
                ),
                *(
                    ModelMessage(role="tool", content="ok", tool_call_id=call.call_id)
                    for call in calls
                ),
            ),
            max_output_tokens=16,
        )
    )
    sent = client.kwargs["messages"]
    assert isinstance(sent, list)
    assistant = next(item for item in sent if item["role"] == "assistant")
    assert assistant["reasoning_content"] == "需要先读这些文件"
    assert len(assistant["tool_calls"]) == 10
    assert [item["role"] for item in sent if item["role"] == "tool"] == ["tool"] * 10
