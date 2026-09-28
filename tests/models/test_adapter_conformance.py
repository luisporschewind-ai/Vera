"""Provider fixture conformance tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vera.config import ProviderConfig
from vera.models.base import FakeModelAdapter, ModelMessage, ModelRequest
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.tools.definitions import ToolDefinition


class _FixtureClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):  # noqa: ANN003
        return self.payload


def _provider(name: str) -> ProviderConfig:
    return ProviderConfig(
        base_url="https://example.test/v1",  # type: ignore[arg-type]
        model=f"{name}-model",
        api_key_env=f"{name.upper()}_API_KEY",
    )


@pytest.mark.parametrize("provider", ["deepseek", "glm"])
def test_fixture_tool_call_conforms(provider: str) -> None:
    path = (
        Path(__file__).resolve().parents[1] / "fixtures" / "providers" / provider / "tool_call.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    adapter = OpenAICompatibleAdapter(_provider(provider), client=_FixtureClient(payload))
    turn = adapter.complete(
        ModelRequest(
            messages=(ModelMessage(role="user", content="read"),),
            tools=(
                ToolDefinition(
                    name="read_file",
                    description="read",
                    input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                ),
            ),
            max_output_tokens=128,
        )
    )
    assert turn.tool_calls[0].name == "read_file"
    assert turn.usage is not None


def test_openai_compatible_adapter_exposes_only_public_model_identity() -> None:
    adapter = OpenAICompatibleAdapter(
        _provider("deepseek"),
        client=_FixtureClient({}),
        api_key="private-provider-key",
        profile_name="deepseek-prod",
        provider_type="deepseek",
    )

    assert adapter.identity is not None
    assert adapter.identity.model_dump(mode="json") == {
        "provider_type": "deepseek",
        "profile_name": "deepseek-prod",
        "model_name": "deepseek-model",
    }
    assert "private-provider-key" not in str(adapter.identity.model_dump())
    assert "example.test" not in str(adapter.identity.model_dump())


def test_fake_adapter_identity_is_unknown_by_default() -> None:
    assert FakeModelAdapter().identity is None
