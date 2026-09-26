"""OpenAI-compatible stream fixture tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from vera.config import ProviderConfig
from vera.models.base import ModelMessage, ModelRequest
from vera.models.capabilities import ModelCapabilities
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.models.streaming import ModelStreamCompleted, ModelTextDelta


class _StreamClient:
    def __init__(self, lines: list[dict]) -> None:
        self.lines = lines
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object):
        assert kwargs.get("stream") is True

        def _gen():
            for payload in self.lines:
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(**(payload["choices"][0].get("delta") or {})),
                            finish_reason=payload["choices"][0].get("finish_reason"),
                        )
                    ],
                    usage=(SimpleNamespace(**payload["usage"]) if "usage" in payload else None),
                    id=payload.get("id"),
                )

        return _gen()


def test_deepseek_stream_reconstructs_final_text() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "providers"
        / "deepseek"
        / "stream_text.jsonl"
    )
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    provider = ProviderConfig(
        base_url="https://example.test/v1",  # type: ignore[arg-type]
        model="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    adapter = OpenAICompatibleAdapter(provider, client=_StreamClient(lines))
    items = tuple(
        adapter.stream(
            ModelRequest(
                messages=(ModelMessage(role="user", content="hi"),),
                max_output_tokens=16,
            )
        )
    )
    assert "".join(item.text for item in items if isinstance(item, ModelTextDelta)) == "完成"
    assert isinstance(items[-1], ModelStreamCompleted)
    assert items[-1].turn.assistant_text == "完成"


def test_stream_usage_option_is_explicit_per_profile() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs: object):
            self.calls.append(kwargs)
            return iter([SimpleNamespace(choices=[], usage=None, id="final")])

    request = ModelRequest(
        messages=(ModelMessage(role="user", content="hi"),), max_output_tokens=16
    )
    base = ProviderConfig(
        base_url="https://example.test/v1",
        model="test",
        api_key_env="TEST_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    client = Client()
    tuple(OpenAICompatibleAdapter(base, client=client).stream(request))
    selected = base.model_copy(update={"stream_usage_mode": "include_usage"})
    tuple(OpenAICompatibleAdapter(selected, client=client).stream(request))
    assert "stream_options" not in client.calls[0]
    assert client.calls[1]["stream_options"] == {"include_usage": True}


def test_stream_reads_usage_only_final_chunk_with_cache_details() -> None:
    class Client:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **_kwargs: object):
            return iter(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="ok"), finish_reason="stop"
                            )
                        ],
                        usage=None,
                        id="s1",
                    ),
                    SimpleNamespace(
                        choices=[],
                        usage={
                            "prompt_tokens": 100,
                            "completion_tokens": 2,
                            "total_tokens": 102,
                            "prompt_tokens_details": {"cached_tokens": 60},
                        },
                        id="s1",
                    ),
                ]
            )

    provider = ProviderConfig(
        base_url="https://example.test/v1",
        model="gpt-4.1-mini",
        api_key_env="OPENAI_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
        stream_usage_mode="include_usage",
    )
    items = tuple(
        OpenAICompatibleAdapter(provider, client=Client()).stream(
            ModelRequest(messages=(ModelMessage(role="user", content="hi"),), max_output_tokens=16)
        )
    )
    assert isinstance(items[-1], ModelStreamCompleted)
    usage = items[-1].turn.usage
    assert usage is not None
    assert (usage.cache_hit_input_tokens, usage.cache_miss_input_tokens) == (60, 40)


def test_stream_reads_reasoning_from_choice_message_when_delta_omits_it() -> None:
    class _StreamClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs: object):
            assert kwargs.get("stream") is True

            def _gen():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None),
                            message=SimpleNamespace(reasoning_content="工具前的思考"),
                            finish_reason="tool_calls",
                        )
                    ],
                    usage=None,
                    id="s-reason",
                )

            return _gen()

    provider = ProviderConfig(
        base_url="https://example.test/v1",  # type: ignore[arg-type]
        model="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    items = tuple(
        OpenAICompatibleAdapter(provider, client=_StreamClient()).stream(
            ModelRequest(
                messages=(ModelMessage(role="user", content="analyze"),),
                max_output_tokens=16,
            )
        )
    )
    assert isinstance(items[-1], ModelStreamCompleted)
    assert items[-1].turn.reasoning_content == "工具前的思考"


def test_stream_collects_reasoning_content_without_leaking_to_text_deltas() -> None:
    lines = [
        {
            "choices": [{"delta": {"reasoning_content": "先列目录"}, "finish_reason": None}],
            "id": "s1",
        },
        {
            "choices": [{"delta": {"content": "完成"}, "finish_reason": "stop"}],
            "id": "s1",
        },
    ]
    provider = ProviderConfig(
        base_url="https://example.test/v1",  # type: ignore[arg-type]
        model="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    adapter = OpenAICompatibleAdapter(provider, client=_StreamClient(lines))
    items = tuple(
        adapter.stream(
            ModelRequest(
                messages=(ModelMessage(role="user", content="hi"),),
                max_output_tokens=16,
            )
        )
    )
    assert [item.text for item in items if isinstance(item, ModelTextDelta)] == ["完成"]
    assert isinstance(items[-1], ModelStreamCompleted)
    assert items[-1].turn.assistant_text == "完成"
    assert items[-1].turn.reasoning_content == "先列目录"


def test_stream_joins_list_content_parts() -> None:
    lines = [
        {
            "choices": [
                {
                    "delta": {"content": [{"type": "text", "text": "入口在 "}]},
                    "finish_reason": None,
                }
            ],
            "id": "s1",
        },
        {
            "choices": [
                {
                    "delta": {"content": [{"type": "text", "text": "main.py。"}]},
                    "finish_reason": "stop",
                }
            ],
            "id": "s1",
        },
    ]
    provider = ProviderConfig(
        base_url="https://example.test/v1",  # type: ignore[arg-type]
        model="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    adapter = OpenAICompatibleAdapter(provider, client=_StreamClient(lines))
    items = tuple(
        adapter.stream(
            ModelRequest(
                messages=(ModelMessage(role="user", content="hi"),),
                max_output_tokens=16,
            )
        )
    )
    assert [item.text for item in items if isinstance(item, ModelTextDelta)] == [
        "入口在 ",
        "main.py。",
    ]
    assert isinstance(items[-1], ModelStreamCompleted)
    assert items[-1].turn.assistant_text == "入口在 main.py。"
