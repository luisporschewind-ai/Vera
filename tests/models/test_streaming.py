"""Model streaming helper tests."""

from __future__ import annotations

from vera.models.base import FakeModelAdapter, ModelMessage, ModelRequest, ModelTurn
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


def test_accumulator_joins_tool_arguments() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push_tool_delta(0, call_id="c1", name="read_", arguments='{"pa')
    accumulator.push_tool_delta(0, name="file", arguments='th":"a.py"}')
    turn = accumulator.finish(finish_reason="tool_calls")
    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "a.py"}
