import shutil
from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry


def test_registry_marks_same_name_as_conflict_and_requires_full_skill_id(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    for root in (builtin, user, workspace):
        root.mkdir()
    write_skill(builtin)
    write_skill(user)
    write_skill(workspace / ".vera" / "skills")
    registry = SkillRegistry(SkillDiscovery(builtin_root=builtin, user_root=user))

    summaries = registry.summaries(workspace)
    assert [item.availability for item in summaries] == ["conflict", "conflict", "conflict"]
    assert registry.resolve("python-review", workspace).reason_codes == ("skill_name_conflict",)
    selected = registry.resolve("user:python-review", workspace)
    assert selected.status == "selected"
    assert selected.skill_id == "user:python-review"


def test_registry_returns_invalid_and_incompatible_summaries_without_path_leak(
    tmp_path: Path,
) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    for root in (builtin, user, workspace):
        root.mkdir()
    package = write_skill(user)
    manifest = package / "skill.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\nunknown = true\n", encoding="utf-8"
    )
    incompatible = write_skill(user, name="incompatible")
    text = incompatible / "skill.toml"
    text.write_text(
        text.read_text(encoding="utf-8")
        .replace('min_vera_core = "0.1.0"', 'min_vera_core = "9.0.0"')
        .replace('max_vera_core_exclusive = "1.0.0"', 'max_vera_core_exclusive = "10.0.0"'),
        encoding="utf-8",
    )

    summaries = SkillRegistry(SkillDiscovery(builtin_root=builtin, user_root=user)).summaries(
        workspace
    )

    by_name = {item.name: item for item in summaries if item.name}
    invalid = next(item for item in summaries if item.reason_codes == ("skill_manifest_invalid",))
    assert invalid.availability == "invalid"
    assert invalid.name is None
    assert invalid.skill_id is None
    assert by_name["incompatible"].availability == "incompatible"
    assert by_name["incompatible"].reason_codes == ("skill_version_incompatible",)
    assert all(str(tmp_path) not in item.model_dump_json() for item in summaries)


def test_registry_rejects_duplicate_full_id_even_after_prior_selection(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user.mkdir()
    workspace.mkdir()
    package = write_skill(user)
    registry = SkillRegistry(SkillDiscovery(builtin_root=builtin, user_root=user))
    prior = registry.resolve("user:python-review", workspace)
    assert prior.status == "selected"
    shutil.copytree(package, user / "duplicate-directory")

    rejected = registry.resolve("user:python-review", workspace)
    assert rejected.status == "invalid"
    assert rejected.reason_codes == ("skill_name_conflict",)
    assert registry.package_for(prior, workspace) is None


def test_registry_refuses_prior_selection_if_new_duplicate_is_incompatible(tmp_path: Path) -> None:
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user.mkdir()
    workspace.mkdir()
    package = write_skill(user)
    registry = SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    prior = registry.resolve("user:python-review", workspace)
    assert prior.status == "selected"

    duplicate = user / "incompatible-directory"
    shutil.copytree(package, duplicate)
    manifest = duplicate / "skill.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        .replace('min_vera_core = "0.1.0"', 'min_vera_core = "9.0.0"')
        .replace('max_vera_core_exclusive = "1.0.0"', 'max_vera_core_exclusive = "10.0.0"'),
        encoding="utf-8",
    )
    assert (
        len(
            [
                item
                for item in registry.summaries(workspace)
                if item.skill_id == "user:python-review"
            ]
        )
        == 2
    )
    assert registry.package_for(prior, workspace) is None
