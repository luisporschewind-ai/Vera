"""Skill recovery fails closed when the private snapshot is unavailable."""

from pathlib import Path

import pytest

from tests.skills.test_manifest import write_skill
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService
from vera.skills.snapshot_store import SkillSnapshotError, SkillSnapshotStore


def test_selected_skill_snapshot_missing_does_not_reload_source(tmp_path: Path) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    user_root.mkdir()
    workspace.mkdir()
    package_root = write_skill(user_root)
    service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user_root))
    )
    selection = service.select("python-review", workspace)
    candidate = service.package_for(selection, workspace)
    assert candidate is not None and candidate.package is not None
    frozen = SkillSnapshotStore().freeze(candidate.package, state_dir=state_dir)
    snapshot_dir = state_dir / "skills" / "snapshots" / "sha256" / frozen.snapshot.snapshot_id
    snapshot_dir.joinpath("snapshot.json").unlink()
    package_root.joinpath("SKILL.md").write_text("changed source\n", encoding="utf-8")

    with pytest.raises(SkillSnapshotError, match="skill_snapshot_missing"):
        SkillSnapshotStore().load(frozen.snapshot.snapshot_id, state_dir=state_dir)

    assert package_root.joinpath("SKILL.md").read_text(encoding="utf-8") == "changed source\n"
