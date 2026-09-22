from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryStage
from vera.contracts.skills import SkillSnapshot
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.recovery.models import RecoverySnapshot


def test_recovery_snapshot_keeps_only_public_skill_snapshot_facts(tmp_path: Path) -> None:
    now = datetime(2026, 9, 21, tzinfo=UTC)
    skill_snapshot = SkillSnapshot(
        snapshot_id="a" * 64,
        skill_id="user:python-review",
        name="python-review",
        version="1.0.0",
        source_kind="user",
        manifest_hash="b" * 64,
        package_hash="c" * 64,
        resource_hash="d" * 64,
    )
    snapshot = RecoverySnapshot(
        run_id="run_skill",
        workspace_root=Path("/tmp/workspace"),
        workspace_identity="e" * 64,
        command=StartRun(
            goal="review", workspace_root=Path("/tmp/workspace"), model_profile="fake"
        ),
        stage=RecoveryStage.STARTED,
        last_event_sequence=1,
        skill_snapshot=skill_snapshot,
        created_at=now,
        updated_at=now,
        vera_version="0.1.0",
    )

    store = RecoverySnapshotStore(tmp_path)
    store.save(snapshot)
    restored = store.load("run_skill")

    assert restored.skill_snapshot == skill_snapshot
    assert "SKILL.md" not in (tmp_path / "runs" / "run_skill" / "recovery.json").read_text()
