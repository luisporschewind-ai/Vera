"""Model streaming helper tests."""

from __future__ import annotations

import pytest

from vera.models.base import FakeModelAdapter, ModelMessage, ModelRequest, ModelTurn
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.streaming import ModelStreamAccumulator, ModelStreamCompleted, ModelTextDelta


def test_default_stream_wraps_complete() -> None:
    adapter = FakeModelAdapter([ModelTurn(assistant_text="完成", finish_reason="stop")])
    request = ModelRequest(
        messages=(ModelMessage(role="user", content="hi"),),
        max_output_tokens=16,
    )
    items = tuple(adapter.stream(request))
    assert len(items) == 1
    assert isinstance(items[0], ModelStreamCompleted)
    assert items[0].turn.assistant_text == "完成"


def test_fake_adapter_emits_text_deltas() -> None:
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="你好", finish_reason="stop")],
        text_deltas=(("你", "好"),),
    )
    request = ModelRequest(
        messages=(ModelMessage(role="user", content="hi"),),
        max_output_tokens=16,
    )
    items = tuple(adapter.stream(request))
    assert [item.text for item in items if isinstance(item, ModelTextDelta)] == ["你", "好"]
    assert isinstance(items[-1], ModelStreamCompleted)


def test_accumulator_keeps_reasoning_content() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push_reasoning("先看目录")
    accumulator.push_text("好的")
    turn = accumulator.finish(finish_reason="stop")
    assert turn.assistant_text == "好的"
    assert turn.reasoning_content == "先看目录"


def test_accumulator_joins_tool_arguments() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push_tool_delta(0, call_id="c1", name="read_", arguments='{"pa')
    accumulator.push_tool_delta(0, name="file", arguments='th":"a.py"}')
    turn = accumulator.finish(finish_reason="tool_calls")
    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "a.py"}
    assert turn.tool_calls[0].parse_error is None


def test_accumulator_invalid_json_sets_parse_error() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push_tool_delta(
        0,
        call_id="c1",
        name="propose_changeset",
        arguments='{"summary":"fifth page","changes":[{"path":',
    )
    turn = accumulator.finish(finish_reason="tool_calls")
    assert turn.tool_calls[0].name == "propose_changeset"
    assert turn.tool_calls[0].arguments == {}
    assert turn.tool_calls[0].parse_error == "invalid_tool_arguments"


def test_accumulator_non_object_json_sets_parse_error() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push_tool_delta(0, call_id="c1", name="read_file", arguments="[]")
    turn = accumulator.finish(finish_reason="tool_calls")
    assert turn.tool_calls[0].parse_error == "invalid_tool_arguments"


def test_accumulator_still_rejects_incomplete_name() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push_tool_delta(0, call_id="c1", arguments='{"path":"a.py"}')
    with pytest.raises(ModelProviderError) as caught:
        accumulator.finish(finish_reason="tool_calls")
    assert caught.value.code is ModelErrorCode.INVALID_RESPONSE
