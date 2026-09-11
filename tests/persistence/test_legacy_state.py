"""Legacy and unsupported run format tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from vera.contracts.recovery import RecoveryClassification
from vera.persistence.run_store import RunFormatStatus, RunStore
from vera.recovery.coordinator import RecoveryCoordinator


def _copy_legacy(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "legacy-v1" / "run_legacy"
    state = tmp_path / "state"
    target = state / "runs" / "run_legacy"
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    return state


def test_legacy_run_remains_visible_but_not_resumable(tmp_path: Path) -> None:
    state = _copy_legacy(tmp_path)
    store = RunStore(state)
    assert store.format_status("run_legacy") is RunFormatStatus.LEGACY
    assert store.read_events("run_legacy")[-1].type == "approval.required"

    report = RecoveryCoordinator(state, "install").scan("run_legacy")[0]
    assert report.classification is RecoveryClassification.LEGACY_NOT_RESUMABLE


def test_corrupt_and_future_formats_are_isolated(tmp_path: Path) -> None:
    state = _copy_legacy(tmp_path)
    corrupt = state / "runs" / "run_corrupt"
    corrupt.mkdir()
    (corrupt / "events.jsonl").write_text("{broken\n", encoding="utf-8")

    future = state / "runs" / "run_future"
    future.mkdir()
    (future / "manifest.json").write_text(
        '{"manifest_version":99,"journal_format_version":1,"run_id":"run_future","created_at":"2026-09-11T00:00:00Z"}',
        encoding="utf-8",
    )
    (future / "events.jsonl").write_text("", encoding="utf-8")

    store = RunStore(state)
    assert store.format_status("run_corrupt") is RunFormatStatus.CORRUPT
    assert store.format_status("run_future") is RunFormatStatus.UNSUPPORTED
    assert store.read_events("run_corrupt") == ()
    ids = {item.run_id for item in store.list_runs()}
    assert "run_legacy" in ids
    assert "run_corrupt" not in ids
    assert "run_future" not in ids
