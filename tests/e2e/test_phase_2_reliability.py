"""Phase-two reliability exit-condition evidence tests."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.commands import InspectRecovery, InspectState, StartRun
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.retry import RetryPolicy
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_phase2_retry_and_inspect_surfaces(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = tmp_path / "state"
    sleeps: list[float] = []
    adapter = FakeModelAdapter(
        [
            ModelProviderError(ModelErrorCode.NETWORK, "network"),
            ModelTurn(assistant_text="recovered", finish_reason="stop"),
        ]
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        state,
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=sleeps.append,
        installation_id="install",
    )
    events = tuple(
        runtime.handle(StartRun(goal="ping", workspace_root=workspace, model_profile="fake"))
    )
    assert any(event.type == "model.retrying" for event in events)
    assert events[-1].type == "run.completed"
    assert sleeps == [0.25]

    inspected = tuple(runtime.handle(InspectRecovery()))
    assert isinstance(inspected, tuple)
    state_events = tuple(runtime.handle(InspectState()))
    assert any(event.type == "state.inspected" for event in state_events)
