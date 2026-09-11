"""Runtime streaming output tests."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.commands import StartRun
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_stream_emits_transient_deltas_and_one_durable_message(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="你好", finish_reason="stop")],
        text_deltas=(("你", "好"),),
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    command = StartRun(goal="hi", workspace_root=workspace, model_profile="fake")
    outputs = tuple(runtime.stream(command))
    frames = [item for item in outputs if isinstance(item, StreamFrame)]
    events = [item for item in outputs if isinstance(item, EventEnvelope)]
    assert [frame.index for frame in frames] == [0, 1]
    assert "".join(str(frame.payload["text"]) for frame in frames) == "你好"
    message = next(event for event in events if event.type == "assistant.message")
    assert message.payload["content"] == "你好"
    context = next(iter(runtime.runs.values()))
    assert all(event.type != "assistant.delta" for event in context.journal.read_all())


def test_handle_filters_stream_frames(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    adapter = FakeModelAdapter(
        [ModelTurn(assistant_text="你好", finish_reason="stop")],
        text_deltas=(("你", "好"),),
    )
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")
    events = tuple(
        runtime.handle(StartRun(goal="hi", workspace_root=workspace, model_profile="fake"))
    )
    assert all(isinstance(event, EventEnvelope) for event in events)
    assert all(event.type != "assistant.delta" for event in events)
    assert any(event.type == "assistant.message" for event in events)
