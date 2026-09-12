import errno
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryStage
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.recovery.models import RecoverySnapshot


def make_snapshot(run_id: str = "run_1", workspace: Path | None = None) -> RecoverySnapshot:
    root = workspace or Path("/tmp/project")
    now = datetime(2026, 9, 11, tzinfo=UTC)
    return RecoverySnapshot(
        run_id=run_id,
        workspace_root=root,
        workspace_identity="a" * 64,
        command=StartRun(goal="edit", workspace_root=root, model_profile="fake"),
        stage=RecoveryStage.STARTED,
        last_event_sequence=1,
        created_at=now,
        updated_at=now,
        vera_version="0.1.0",
    )


def test_snapshot_save_is_atomic_and_private(tmp_path: Path) -> None:
    snapshot = make_snapshot()
    store = RecoverySnapshotStore(tmp_path / "state")
    store.save(snapshot)

    target = tmp_path / "state" / "runs" / snapshot.run_id / "recovery.json"
    assert store.load(snapshot.run_id) == snapshot
    assert store.exists(snapshot.run_id)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert not target.with_suffix(".json.tmp").exists()


def test_corrupt_snapshot_has_stable_error(tmp_path: Path) -> None:
    target = tmp_path / "state" / "runs" / "run_1" / "recovery.json"
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    with pytest.raises(RecoverySnapshotError) as caught:
        RecoverySnapshotStore(tmp_path / "state").load("run_1")
    assert caught.value.code == "mid_file_corrupt"


def test_failed_replace_keeps_existing_snapshot_bytes(tmp_path: Path) -> None:
    snapshot = make_snapshot()
    store = RecoverySnapshotStore(tmp_path / "state")
    store.save(snapshot)
    target = tmp_path / "state" / "runs" / snapshot.run_id / "recovery.json"
    original = target.read_bytes()

    def fail_replace(_source: Path, _dest: Path) -> None:
        raise OSError("injected replace failure")

    failing = RecoverySnapshotStore(tmp_path / "state", replace=fail_replace)
    updated = snapshot.model_copy(update={"last_event_sequence": 2, "vera_version": "0.1.1"})
    with pytest.raises(RecoverySnapshotError, match="snapshot_write_failed"):
        failing.save(updated)

    assert target.read_bytes() == original
    assert not target.with_suffix(".json.tmp").exists()
    assert store.load(snapshot.run_id) == snapshot


def test_snapshot_enospc_does_not_clobber(tmp_path: Path) -> None:
    snapshot = make_snapshot()
    store = RecoverySnapshotStore(tmp_path / "state")
    store.save(snapshot)
    target = tmp_path / "state" / "runs" / snapshot.run_id / "recovery.json"
    original = target.read_bytes()

    def fail_fsync(_fd: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    failing = RecoverySnapshotStore(tmp_path / "state", fsync=fail_fsync)
    updated = snapshot.model_copy(update={"last_event_sequence": 9})
    with pytest.raises(RecoverySnapshotError) as caught:
        failing.save(updated)
    assert caught.value.code == "no_space"
    assert target.read_bytes() == original
    assert not target.with_suffix(".json.tmp").exists()


def test_missing_snapshot_is_a_stable_error(tmp_path: Path) -> None:
    with pytest.raises(RecoverySnapshotError, match="missing_snapshot"):
        RecoverySnapshotStore(tmp_path / "state").load("run_1")
    assert RecoverySnapshotStore(tmp_path / "state").exists("run_1") is False


def test_unsafe_run_id_is_rejected(tmp_path: Path) -> None:
    store = RecoverySnapshotStore(tmp_path / "state")
    snapshot = make_snapshot(run_id="../escape")
    with pytest.raises(RecoverySnapshotError, match="invalid_run_id"):
        store.save(snapshot)
    with pytest.raises(RecoverySnapshotError, match="invalid_run_id"):
        store.load("../escape")
