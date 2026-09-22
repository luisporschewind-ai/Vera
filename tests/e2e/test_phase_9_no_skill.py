"""Phase 9 NoSkill acceptance matrix."""

from pathlib import Path

from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_phase_9_no_skill_is_zero_control_plane_by_default(tmp_path: Path) -> None:
    state = tmp_path / "state"
    adapter = FakeModelAdapter([ModelTurn(assistant_text="done", finish_reason="stop")])
    runtime = VeraRuntime(adapter, ToolRegistry(), state)

    events = tuple(
        runtime.handle(StartRun(goal="hello", workspace_root=tmp_path, model_profile="fake"))
    )

    assert all(not event.type.startswith("skill.") for event in events)
    assert not (state / "skills").exists()
    assert all(run.skill_snapshot is None for run in runtime.runs.values())
    assert all("skill" not in event.payload for event in events if event.type == "run.started")
