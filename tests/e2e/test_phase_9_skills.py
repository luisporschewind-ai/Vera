"""Offline Phase 9 matrix for Core-native Skills."""

from __future__ import annotations

import json
from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService
from vera.tools.registry import ToolRegistry


def test_phase_9_skill_matrix_covers_sources_conflicts_and_recovery(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    builtin.mkdir()
    user.mkdir()
    workspace.mkdir()
    write_skill(builtin, name="builtin-review")
    write_skill(user, name="user-review")
    write_skill(workspace / ".vera" / "skills", name="workspace-review")
    conflict_user = write_skill(user, name="conflict-review")
    write_skill(builtin, name="conflict-review")
    invalid = user / "invalid-review"
    invalid.mkdir()
    (invalid / "skill.toml").write_text("format_version = 99\n", encoding="utf-8")

    service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=builtin, user_root=user))
    )
    summaries = service.registry.summaries(workspace)
    summary_by_id = {item.skill_id: item for item in summaries}

    assert {
        "builtin:builtin-review",
        "user:user-review",
        "workspace:workspace-review",
        "builtin:conflict-review",
        "user:conflict-review",
    } <= set(summary_by_id)
    assert summary_by_id["user:conflict-review"].availability == "conflict"
    assert any(
        item.availability == "invalid" and "skill_manifest_version_unsupported" in item.reason_codes
        for item in summaries
    )
    assert service.registry.resolve("conflict-review", workspace).reason_codes == (
        "skill_name_conflict",
    )
    assert service.registry.resolve("user:conflict-review", workspace).status == "selected"
    assert service.registry.resolve("user:user-review", workspace).status == "selected"

    service.select("workspace-review", workspace)
    adapter = FakeModelAdapter([ModelTurn(assistant_text="done", finish_reason="stop")])
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        state,
        skill_selection_service=service,
    )
    events = tuple(
        runtime.handle(StartRun(goal="review", workspace_root=workspace, model_profile="fake"))
    )
    bound = next(event for event in events if event.type == "skill.snapshot.bound")
    assert bound.payload["source_kind"] == "workspace"
    assert all(
        "# Skill" not in json.dumps(event.payload, ensure_ascii=False)
        for event in events
        if event.type.startswith("skill.") and event.type != "skill.content.loaded"
    )
    run_id = next(event.run_id for event in events if event.type == "run.started")
    snapshot = runtime.runs[run_id].skill_snapshot
    assert snapshot is not None
    assert snapshot.source_kind == "workspace"
    assert str(conflict_user) not in json.dumps(bound.payload)
