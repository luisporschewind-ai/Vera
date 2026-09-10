from pathlib import Path

from vera.config import Limits
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_three_identical_tool_calls_fail_without_writes(tmp_path: Path) -> None:
    turn = ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(call_id="1", name="missing", arguments={"path": "hello.txt"}),
        ),
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
