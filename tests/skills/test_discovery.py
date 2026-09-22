from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.skills.discovery import SkillDiscovery


def test_discovery_scans_only_direct_child_directories_in_allowed_roots(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    builtin.mkdir()
    user.mkdir()
    workspace.mkdir()
    write_skill(builtin)
    write_skill(user)
    write_skill(user / "nested", name="hidden")
    write_skill(workspace / ".vera" / "skills")
    (user / "not-a-package").mkdir()
    (user / "not-a-package" / "ignored.txt").write_text("ignored", encoding="utf-8")

    candidates = SkillDiscovery(builtin_root=builtin, user_root=user).discover(workspace)

    assert [(item.source_kind, item.package_root.name) for item in candidates] == [
        ("builtin", "python-review"),
        ("user", "nested"),
        ("user", "not-a-package"),
        ("user", "python-review"),
        ("workspace", "python-review"),
    ]
    assert all(item.package_root.name != "hidden" for item in candidates)


def test_discovery_reports_symlink_package_without_following_it(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    for root in (builtin, user, workspace):
        root.mkdir()
    real = write_skill(tmp_path / "real")
    (user / "linked").symlink_to(real, target_is_directory=True)

    candidates = SkillDiscovery(builtin_root=builtin, user_root=user).discover(workspace)

    linked = next(item for item in candidates if item.package_root.name == "linked")
    assert linked.summary.availability == "invalid"
    assert linked.summary.reason_codes == ("skill_symlink_refused",)
