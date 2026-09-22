from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.skills.test_manifest import write_skill
from vera.skills.manifest import ManifestLoader
from vera.skills.snapshot_store import (
    SkillSnapshotStore,
    SnapshotReferenceReport,
)


def _freeze(tmp_path: Path, *, state_dir: Path, created_at: datetime, name: str = "python-review"):
    package = ManifestLoader().load(write_skill(tmp_path / "source", name=name), source_kind="user")
    return SkillSnapshotStore().freeze(
        package,
        state_dir=state_dir,
        created_at=created_at,
    )


def test_collect_keeps_recent_and_referenced_snapshots(tmp_path: Path) -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    state_dir = tmp_path / "state"
    old = _freeze(
        tmp_path / "old", state_dir=state_dir, created_at=now - timedelta(days=31), name="old-skill"
    )
    recent = _freeze(
        tmp_path / "recent",
        state_dir=state_dir,
        created_at=now - timedelta(days=1),
        name="recent-skill",
    )
    referenced = _freeze(
        tmp_path / "referenced",
        state_dir=state_dir,
        created_at=now - timedelta(days=31),
        name="referenced-skill",
    )
    store = SkillSnapshotStore()

    result = store.collect(
        now=now,
        references=SnapshotReferenceReport(referenced_ids=(referenced.snapshot_id,)),
        state_dir=state_dir,
    )

    assert old.snapshot_id in result.deleted_ids
    assert recent.snapshot_id in result.retained_ids
    assert referenced.snapshot_id in result.retained_ids


def test_collect_refuses_when_reference_scan_is_uncertain(tmp_path: Path) -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    state_dir = tmp_path / "state"
    frozen = _freeze(
        tmp_path / "source",
        state_dir=state_dir,
        created_at=now - timedelta(days=31),
        name="uncertain-skill",
    )

    result = SkillSnapshotStore().collect(
        now=now,
        references=SnapshotReferenceReport(referenced_ids=(), uncertain=True),
        state_dir=state_dir,
    )

    assert frozen.snapshot_id in result.refused_ids
    assert result.reason_code == "skill_snapshot_cleanup_refused"
    assert (state_dir / "skills" / "snapshots" / "sha256" / frozen.snapshot_id).exists()
