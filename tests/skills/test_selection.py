from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService


def test_selection_is_explicit_clearable_and_consumed_once(tmp_path: Path) -> None:
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user.mkdir()
    workspace.mkdir()
    write_skill(user)
    service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )

    selected = service.select("python-review", workspace)

    assert selected.status == "selected"
    assert service.pending == selected
    consumed = service.consume_for_run(workspace)
    assert consumed == selected
    assert service.pending.mode == "none"
    assert service.clear().mode == "none"


def test_invalid_selection_preserves_selector_and_does_not_fallback(tmp_path: Path) -> None:
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user.mkdir()
    workspace.mkdir()
    write_skill(user)
    service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )

    invalid = service.select("workspace:python-review", workspace)

    assert invalid.status == "invalid"
    assert invalid.selector == "workspace:python-review"
    assert service.pending == invalid
    assert service.consume_for_run(workspace) == invalid
    assert service.pending == invalid
