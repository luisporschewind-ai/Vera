"""External workspace and user Skill roots remain install-safe."""

from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService


def test_external_user_and_workspace_skills_are_discovered_without_repo_paths(
    tmp_path: Path,
) -> None:
    user_root = tmp_path / "user-config" / "Vera" / "skills"
    workspace = tmp_path / "external-workspace"
    user_root.mkdir(parents=True)
    (workspace / ".vera" / "skills").mkdir(parents=True)
    write_skill(user_root, name="user-review")
    write_skill(workspace / ".vera" / "skills", name="workspace-review")

    service = SkillSelectionService(
        SkillRegistry(
            SkillDiscovery(
                builtin_root=tmp_path / "missing-builtin",
                user_root=user_root,
            )
        )
    )

    summaries = service.registry.summaries(workspace)
    selected_user = service.select("user:user-review", workspace)
    selected_workspace = service.registry.resolve("workspace-review", workspace)

    assert {item.skill_id for item in summaries} == {
        "user:user-review",
        "workspace:workspace-review",
    }
    assert selected_user.status == "selected"
    assert selected_workspace.status == "selected"
    assert str(tmp_path) not in str(summaries)
