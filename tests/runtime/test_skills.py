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


def test_selected_skill_is_bound_before_model_request_and_snapshot_is_durable(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    user = tmp_path / "user"
    workspace.mkdir()
    user.mkdir()
    write_skill(user)
    selection = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )
    selection.select("python-review", workspace)
    adapter = FakeModelAdapter([ModelTurn(assistant_text="收到", finish_reason="stop")])
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        tmp_path / "state",
        skill_selection_service=selection,
    )

    events = list(
        runtime.handle(StartRun(goal="review", workspace_root=workspace, model_profile="fake"))
    )

    bound = next(event for event in events if event.type == "skill.snapshot.bound")
    run_id = next(event.run_id for event in events if event.type == "run.started")
    assert bound.payload["skill_id"] == "user:python-review"
    assert bound.payload["snapshot_id"]
    assert runtime.runs[run_id].skill_snapshot is not None
    assert any("# Skill" in message.content for message in adapter.requests[0].messages)
    assert "# Skill" not in json.dumps(bound.payload)


def test_no_skill_does_not_scan_or_add_skill_event(tmp_path: Path) -> None:
    adapter = FakeModelAdapter([ModelTurn(assistant_text="完成", finish_reason="stop")])
    runtime = VeraRuntime(adapter, ToolRegistry(), tmp_path / "state")

    events = list(
        runtime.handle(StartRun(goal="hello", workspace_root=tmp_path, model_profile="fake"))
    )

    assert all(not event.type.startswith("skill.") for event in events)
    assert not (tmp_path / "state" / "skills").exists()
