from pathlib import Path

from tests.recovery.helpers import make_snapshot
from vera.contracts.recovery import RecoveryClassification, RecoveryStage
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.recovery.coordinator import RecoveryCoordinator
from vera.redaction import Redactor
from vera.workspace.changeset import sha256_bytes


def _journal(state_dir: Path, run_id: str, kind: str = "task") -> EventJournal:
    journal = EventJournal(state_dir, run_id, Redactor([]))
    journal.append(
        "run.started",
        {
            "goal": "edit",
            "workspace_root": str(state_dir.parent / "workspace"),
            "model_profile": "fake",
            "kind": kind,
        },
    )
    return journal


def test_coordinator_isolates_corrupt_legacy_and_skips_terminal(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("before\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    store = RecoverySnapshotStore(state_dir)

    healthy = _journal(state_dir, "run_healthy")
    healthy.append("approval.required", {"kind": "changeset"})
    store.save(
        make_snapshot(
            workspace,
            files=(("app.py", "update", b"before\n", b"after\n"),),
        ).model_copy(update={"run_id": "run_healthy"})
    )

    _journal(state_dir, "run_corrupt")
    target = state_dir / "runs" / "run_corrupt" / "recovery.json"
    target.write_text("{broken", encoding="utf-8")

    _journal(state_dir, "run_legacy")

    done = _journal(state_dir, "run_done")
    done.append("run.completed", {"state": "completed"})
    store.save(
        make_snapshot(
            workspace,
            files=(("app.py", "update", b"before\n", b"after\n"),),
            stage=RecoveryStage.TERMINAL,
            pending=False,
        ).model_copy(update={"run_id": "run_done"})
    )

    compact = _journal(state_dir, "run_compact", kind="compaction")
    compact.append("run.completed", {"state": "completed", "outcome": "compacted"})

    reports = RecoveryCoordinator(state_dir, "install-1").scan()
    by_id = {item.run_id: item for item in reports}

    assert set(by_id) == {"run_healthy", "run_corrupt", "run_legacy"}
    assert by_id["run_healthy"].classification is RecoveryClassification.RESUMABLE_APPROVAL
    assert by_id["run_corrupt"].classification is RecoveryClassification.MANUAL_REQUIRED
    assert by_id["run_legacy"].classification is RecoveryClassification.LEGACY_NOT_RESUMABLE


def test_repeated_scan_is_read_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("before\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    _journal(state_dir, "run_1")
    RecoverySnapshotStore(state_dir).save(
        make_snapshot(workspace).model_copy(update={"run_id": "run_1"})
    )
    coordinator = RecoveryCoordinator(state_dir, "install-1")

    def digest() -> dict[str, str]:
        values: dict[str, str] = {}
        for path in sorted(tmp_path.rglob("*")):
            if path.is_file():
                values[str(path.relative_to(tmp_path))] = sha256_bytes(path.read_bytes())
        return values

    before = digest()
    first = coordinator.scan()
    second = coordinator.scan("run_1")
    assert digest() == before
    assert first == second
