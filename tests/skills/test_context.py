from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.skills.context import SkillContextAssembler
from vera.skills.manifest import ManifestLoader
from vera.skills.snapshot_store import SkillSnapshotStore


def test_context_assembly_is_ordered_provenanced_and_body_free_in_facts(tmp_path: Path) -> None:
    package = ManifestLoader().load(write_skill(tmp_path / "source"), source_kind="user")
    frozen = SkillSnapshotStore().freeze(package, state_dir=tmp_path / "state")

    parts = SkillContextAssembler().assemble(frozen)

    assert [part.envelope.origin.rsplit(":", 1)[-1] for part in parts] == [
        "SKILL.md",
        "references/checklist.md",
        "templates/report.md",
    ]
    assert all(part.envelope.source_kind == "skill_content" for part in parts)
    assert all(part.envelope.trust_level.value == "advisory" for part in parts)
    assert all("# Skill" not in part.envelope.model_dump_json() for part in parts)
    assert "# Skill" in parts[0].text


def test_workspace_context_is_untrusted_and_cannot_become_policy(tmp_path: Path) -> None:
    package = ManifestLoader().load(write_skill(tmp_path / "source"), source_kind="workspace")
    frozen = SkillSnapshotStore().freeze(package, state_dir=tmp_path / "state")

    parts = SkillContextAssembler().assemble(frozen)

    assert all(part.envelope.trust_level.value == "untrusted" for part in parts)
    assert all(part.envelope.trust_level.value != "builtin_policy" for part in parts)
