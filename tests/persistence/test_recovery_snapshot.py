import errno
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.changes import ChangeSet, FileChange
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryStage
from vera.contracts.verification import VerificationCommand
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.recovery.models import PersistedChangeSet, RecoverySnapshot
from vera.verification.runner import VerificationRunner


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


def test_legacy_v1_changeset_without_artifact_plan_decodes(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "changeset_id": "changeset_1",
        "run_id": "run_1",
        "summary": "更新问候语",
        "files": [
            {
                "schema_version": 1,
                "operation": "update",
                "path": "hello.txt",
                "before_hash": "before",
                "after_hash": "after",
                "unified_diff": "@@ -1 +1 @@",
            }
        ],
        "verification": [
            {
                "argv": ["pytest", "-q"],
                "cwd": ".",
                "timeout_seconds": 120,
                "required": True,
            }
        ],
        "content_hash": "content_hash",
    }
    restored = ChangeSet.model_validate(payload)
    assert restored.verification[0].artifact_plan is None
    assert FileChange.model_validate(payload["files"][0]).path == "hello.txt"


def test_legacy_v1_recovery_snapshot_without_artifact_plan_is_unplanned(
    tmp_path: Path,
) -> None:
    after = b"new\n"
    snapshot = RecoverySnapshot(
        run_id="run_1",
        workspace_root=tmp_path,
        workspace_identity="a" * 64,
        command=StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"),
        stage=RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
        last_event_sequence=1,
        built_changeset=PersistedChangeSet(
            change_set=ChangeSet(
                changeset_id="cs_1",
                run_id="run_1",
                summary="edit",
                files=(),
                verification=(VerificationCommand(argv=("pytest", "-q"), cwd="."),),
                content_hash="hash",
            ),
            intended_content_b64={},
        ),
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
        updated_at=datetime(2026, 9, 11, tzinfo=UTC),
        vera_version="0.1.0",
    )
    raw = json.loads(snapshot.model_dump_json())
    raw["built_changeset"]["change_set"]["verification"] = [
        {"argv": ["pytest", "-q"], "cwd": ".", "timeout_seconds": 120, "required": True}
    ]
    restored = RecoverySnapshot.model_validate(raw)
    command = restored.built_changeset.change_set.verification[0]  # type: ignore[union-attr]
    assert command.artifact_plan is None
    result = VerificationRunner(tmp_path).run(command)
    assert result.status == "rejected"
    assert result.reason_code == "verification_not_planned"
    del after
