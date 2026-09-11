"""State migration dry-run and apply tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from vera.persistence.migration import StateMigrationService
from vera.persistence.run_manifest import RunManifestStore
from vera.persistence.run_store import RunFormatStatus, RunStore


def _legacy_state(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "legacy-v1" / "run_legacy"
    state = tmp_path / "state"
    target = state / "runs" / "run_legacy"
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    return state


def test_migration_apply_never_rewrites_journal(tmp_path: Path) -> None:
    legacy_state = _legacy_state(tmp_path)
    events_path = legacy_state / "runs" / "run_legacy" / "events.jsonl"
    before = events_path.read_bytes()
    service = StateMigrationService(legacy_state)
    plan = service.plan("run_legacy")
    result = service.apply(plan)

    assert result.status == "completed"
    assert events_path.read_bytes() == before
    backup = events_path.parent / "migration-backup" / plan.migration_id / "events.jsonl"
    assert backup.read_bytes() == before
    assert RunManifestStore(legacy_state).load("run_legacy").journal_format_version == 1
    assert RunStore(legacy_state).format_status("run_legacy") is RunFormatStatus.CURRENT


def test_migration_hash_mismatch_does_not_write(tmp_path: Path) -> None:
    legacy_state = _legacy_state(tmp_path)
    service = StateMigrationService(legacy_state)
    plan = service.plan("run_legacy")
    bad = plan.model_copy(update={"migration_hash": "0" * 64})
    result = service.apply(bad)
    assert result.status == "failed"
    assert result.reason_code == "migration_hash_mismatch"
    assert not (legacy_state / "runs" / "run_legacy" / "manifest.json").exists()


def test_failed_replace_keeps_legacy_readable(tmp_path: Path) -> None:
    legacy_state = _legacy_state(tmp_path)
    events_path = legacy_state / "runs" / "run_legacy" / "events.jsonl"
    before = events_path.read_bytes()
    service = StateMigrationService(legacy_state)
    plan = service.plan("run_legacy")

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("injected")

    result = service.apply(plan, replace=fail_replace)
    assert result.status == "failed"
    assert events_path.read_bytes() == before
    assert RunStore(legacy_state).format_status("run_legacy") is RunFormatStatus.LEGACY
    backup = events_path.parent / "migration-backup" / plan.migration_id / "events.jsonl"
    assert backup.read_bytes() == before
