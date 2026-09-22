from __future__ import annotations

from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.runtime.engine import VeraRuntime
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService
from vera.tools.registry import ToolRegistry


def test_recovery_reloads_bound_skill_snapshot_not_source_package(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    user = tmp_path / "user"
    workspace.mkdir()
    user.mkdir()
    package_root = write_skill(user)
    selection = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )
    selection.select("python-review", workspace)
    state_dir = tmp_path / "state"
    runtime = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="等待", finish_reason="stop")]),
        ToolRegistry(),
        state_dir,
        skill_selection_service=selection,
    )

    events = list(
        runtime.handle(StartRun(goal="review", workspace_root=workspace, model_profile="fake"))
    )
    run_id = next(event.run_id for event in events if event.type == "run.started")
    snapshot = RecoverySnapshotStore(state_dir).load(run_id)
    assert snapshot.skill_snapshot is not None

    (package_root / "SKILL.md").write_text("changed source\n", encoding="utf-8")
    restored_runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir)
    context = restored_runtime._context_from_snapshot(run_id)

    assert context.skill_snapshot == snapshot.skill_snapshot
    assert "# Skill" in context.skill_context[0].text
    assert "changed source" not in context.skill_context[0].text
