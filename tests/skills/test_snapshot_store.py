from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests.skills.test_manifest import write_skill
from vera.skills.manifest import ManifestLoader
from vera.skills.snapshot_store import SkillSnapshotError, SkillSnapshotStore


def _package(root: Path, *, source_kind: str = "user"):
    package_root = write_skill(root)
    return ManifestLoader().load(package_root, source_kind=source_kind)  # type: ignore[arg-type]


def test_freeze_is_content_addressed_private_and_source_path_free(tmp_path: Path) -> None:
    package = _package(tmp_path / "source")
    store = SkillSnapshotStore()

    frozen = store.freeze(package, state_dir=tmp_path / "state")
    snapshot_root = tmp_path / "state" / "skills" / "snapshots" / "sha256" / frozen.snapshot_id
    metadata = snapshot_root / "snapshot.json"

    assert len(frozen.snapshot_id) == 64
    assert [item.relative_path for item in frozen.context_files()] == [
        "SKILL.md",
        "references/checklist.md",
        "templates/report.md",
    ]
    assert stat.S_IMODE(snapshot_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(metadata.stat().st_mode) == 0o600
    assert str(package.package_root) not in metadata.read_text(encoding="utf-8")
    assert "# Skill" not in frozen.snapshot.model_dump_json()

    same = store.freeze(package, state_dir=tmp_path / "state")
    other_source = _package(tmp_path / "workspace", source_kind="workspace")
    other = store.freeze(other_source, state_dir=tmp_path / "state")
    assert same.snapshot_id == frozen.snapshot_id
    assert other.snapshot_id != frozen.snapshot_id


def test_freeze_rejects_source_change_without_publishing_partial_snapshot(tmp_path: Path) -> None:
    package_root = write_skill(tmp_path / "source")
    package = ManifestLoader().load(package_root, source_kind="user")
    (package_root / "SKILL.md").write_text("changed\n", encoding="utf-8")
    state_dir = tmp_path / "state"

    with pytest.raises(SkillSnapshotError, match="skill_source_changed"):
        SkillSnapshotStore().freeze(package, state_dir=state_dir)

    snapshot_root = state_dir / "skills" / "snapshots" / "sha256"
    assert not snapshot_root.exists() or not tuple(snapshot_root.iterdir())


def test_load_rejects_missing_corrupt_and_tampered_snapshot(tmp_path: Path) -> None:
    package = _package(tmp_path / "source")
    state_dir = tmp_path / "state"
    store = SkillSnapshotStore()
    frozen = store.freeze(package, state_dir=state_dir)

    assert store.load(frozen.snapshot_id, state_dir=state_dir).snapshot == frozen.snapshot
    with pytest.raises(SkillSnapshotError, match="skill_snapshot_missing"):
        store.load("0" * 64, state_dir=state_dir)

    metadata = state_dir / "skills" / "snapshots" / "sha256" / frozen.snapshot_id / "snapshot.json"
    original = metadata.read_bytes()
    metadata.write_bytes(original.replace(b"python-review", b"tampered-review"))
    with pytest.raises(SkillSnapshotError, match="skill_snapshot_corrupt"):
        store.load(frozen.snapshot_id, state_dir=state_dir)


def test_scan_references_is_conservative(tmp_path: Path) -> None:
    package = _package(tmp_path / "source")
    state_dir = tmp_path / "state"
    frozen = SkillSnapshotStore().freeze(package, state_dir=state_dir)

    report = SkillSnapshotStore().scan_references(
        runs=(
            {"snapshot_id": frozen.snapshot_id},
            {"snapshot_id": "bad"},
        ),
        sessions=(),
    )

    assert frozen.snapshot_id in report.referenced_ids
    assert report.uncertain is True
