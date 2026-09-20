"""NoSkill remains the default compatibility path."""

from pathlib import Path

from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_legacy_no_skill_run_keeps_event_and_state_boundaries(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    adapter = FakeModelAdapter([ModelTurn(assistant_text="完成", finish_reason="stop")])
    runtime = VeraRuntime(adapter, ToolRegistry(), state_dir)

    events = tuple(
        runtime.handle(StartRun(goal="hello", workspace_root=tmp_path, model_profile="fake"))
    )

    assert all(not event.type.startswith("skill.") for event in events)
    assert not (state_dir / "skills").exists()
    assert runtime.runs
    assert all(run.skill_snapshot is None for run in runtime.runs.values())
