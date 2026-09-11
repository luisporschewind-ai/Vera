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
