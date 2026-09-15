from pathlib import Path

from vera.config import Limits
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_three_identical_tool_calls_fail_without_writes(tmp_path: Path) -> None:
    turn = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="1", name="missing", arguments={"path": "hello.txt"}),),
    )
    events = list(
        VeraRuntime(
            FakeModelAdapter([turn, turn, turn]),
            ToolRegistry(),
            tmp_path / "state",
            limits=Limits(max_model_turns=5),
        ).handle(StartRun(goal="inspect", workspace_root=tmp_path, model_profile="fake"))
    )
    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "repeated_tool_call"


def test_nonconsecutive_identical_calls_do_not_fail(tmp_path: Path) -> None:
    list_turn = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="list", name="list_directory", arguments={"path": "."}),),
    )
    read_turn = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(call_id="read", name="read_file", arguments={"path": "a.swift"}),
        ),
    )
    events = list(
        VeraRuntime(
            FakeModelAdapter(
                [
                    list_turn,
                    read_turn,
                    list_turn,
                    read_turn,
                    list_turn,
                    ModelTurn(assistant_text="这是一个小示例项目。", finish_reason="stop"),
                ]
            ),
            ToolRegistry(),
            tmp_path / "state",
            limits=Limits(max_model_turns=8),
        ).handle(StartRun(goal="analyze", workspace_root=tmp_path, model_profile="fake"))
    )
    assert events[-1].type == "run.completed"
    assert all(event.payload.get("reason") != "repeated_tool_call" for event in events)


def test_tool_limit_wraps_up_with_final_answer(tmp_path: Path) -> None:
    tool = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="1", name="list_directory", arguments={"path": "."}),),
    )
    events = list(
        VeraRuntime(
            FakeModelAdapter(
                [
                    tool,
                    tool,
                    tool,
                    ModelTurn(assistant_text="这是根据已有文件得出的结构。", finish_reason="stop"),
                ]
            ),
            ToolRegistry(),
            tmp_path / "state",
            limits=Limits(max_tool_calls=2, max_model_turns=8),
        ).handle(StartRun(goal="analyze", workspace_root=tmp_path, model_profile="fake"))
    )
    assert events[-1].type == "run.completed"
    assert any(
        event.type == "assistant.message" and "结构" in str(event.payload.get("content", ""))
        for event in events
    )


def test_tool_limit_still_fails_when_wrap_up_returns_tools(tmp_path: Path) -> None:
    tool = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="1", name="list_directory", arguments={"path": "."}),),
    )
    events = list(
        VeraRuntime(
            FakeModelAdapter([tool, tool, tool, tool]),
            ToolRegistry(),
            tmp_path / "state",
            limits=Limits(max_tool_calls=2, max_model_turns=8),
        ).handle(StartRun(goal="analyze", workspace_root=tmp_path, model_profile="fake"))
    )
    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "max_tool_calls"
