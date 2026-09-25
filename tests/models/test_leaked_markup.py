"""Leaked provider tool-call markup detection and stream filtering."""

from __future__ import annotations

from types import SimpleNamespace

from vera.config import ProviderConfig
from vera.models.base import ModelMessage, ModelRequest
from vera.models.capabilities import ModelCapabilities
from vera.models.leaked_markup import (
    LeakedMarkupFilter,
    find_leaked_tool_markup,
    strip_leaked_tool_markup,
)
from vera.models.openai_compatible import OpenAICompatibleAdapter
from vera.models.streaming import ModelStreamCompleted, ModelTextDelta

_LEAK = (
    '<｜DSML｜function_calls><｜DSML｜invoke name="propose_changeset">'
    '<｜DSML｜parameter name="summary" string="true">创建 VERA.md</｜DSML｜parameter>'
    "</｜DSML｜invoke></｜DSML｜function_calls>"
)


def test_find_and_strip_leaked_markup() -> None:
    text = f"现在提交提案：\n\n{_LEAK}"
    assert find_leaked_tool_markup(text) == text.index("<｜DSML｜")
    assert strip_leaked_tool_markup(text) == "现在提交提案："
    assert find_leaked_tool_markup('<|DSML|invoke name="x">') == 0
    assert find_leaked_tool_markup("<｜tool▁calls▁begin｜>") == 0
    assert find_leaked_tool_markup("比较 a < b 与 `<div>`") is None
    assert find_leaked_tool_markup(None) is None
    assert strip_leaked_tool_markup("普通回答") == "普通回答"


def test_filter_passes_plain_text_unchanged() -> None:
    stream = LeakedMarkupFilter()
    assert stream.push("入口在 ") == "入口在 "
    assert stream.push("a < b。") == "a < b。"
    assert stream.flush() == ""
    assert not stream.leaked


def test_filter_holds_split_marker_and_suppresses_rest() -> None:
    stream = LeakedMarkupFilter()
    shown = [stream.push(part) for part in ("提交提案：<", "｜DS", "ML｜invoke", " name=")]
    assert "".join(shown) == "提交提案："
    assert stream.leaked
    assert stream.push("更多内容") == ""
    assert stream.flush() == ""


def test_filter_releases_held_prefix_that_is_not_a_marker() -> None:
    stream = LeakedMarkupFilter()
    assert stream.push("比较 <") == "比较 "
    assert stream.push("｜") == ""
    assert stream.push("普通") == "<｜普通"
    assert stream.push("结尾 <") == "结尾 "
    assert stream.flush() == "<"


class _Client:
    def __init__(self, parts: list[str]) -> None:
        self.parts = parts
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object):
        def _gen():
            for index, part in enumerate(self.parts):
                last = index == len(self.parts) - 1
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=part),
                            finish_reason="stop" if last else None,
                        )
                    ],
                    usage=None,
                    id="s-leak",
                )

        return _gen()


def test_adapter_stream_hides_leaked_markup_but_keeps_full_text() -> None:
    parts = ["现在提交提案：", "\n\n<｜DS", _LEAK[len("<｜DS") : 40], _LEAK[40:]]
    provider = ProviderConfig(
        base_url="https://example.test/v1",  # type: ignore[arg-type]
        model="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    items = tuple(
        OpenAICompatibleAdapter(provider, client=_Client(parts)).stream(
            ModelRequest(
                messages=(ModelMessage(role="user", content="hi"),),
                max_output_tokens=16,
            )
        )
    )
    shown = "".join(item.text for item in items if isinstance(item, ModelTextDelta))
    assert shown == "现在提交提案：\n\n"
    assert "DSML" not in shown
    assert isinstance(items[-1], ModelStreamCompleted)
    assert items[-1].turn.assistant_text == "".join(parts)
    assert items[-1].turn.tool_calls == ()
