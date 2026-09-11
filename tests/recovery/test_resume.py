from pathlib import Path

import pytest

from tests.recovery.helpers import make_snapshot
from vera.contracts.recovery import RecoveryClassification, RecoveryStage
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.resume import ResumeRejected, RunResumer
from vera.redaction import Redactor
from vera.runtime.state import RunState


def _seed_approval_run(tmp_path: Path, run_id: str = "run_1") -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("before\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    journal = EventJournal(state_dir, run_id, Redactor([]))
    journal.append(
        "run.started",
        {
            "goal": "edit",
            "workspace_root": str(workspace),
            "model_profile": "fake",
            "kind": "task",
        },
    )
    journal.append("changeset.proposed", {"changeset_id": "cs_1"})
    journal.append("approval.required", {"approval_id": "approval_1"})
    RecoverySnapshotStore(state_dir).save(
        make_snapshot(workspace).model_copy(update={"run_id": run_id})
    )
    return state_dir


def test_prepare_resume_returns_current_classification(tmp_path: Path) -> None:
    state_dir = _seed_approval_run(tmp_path)
    coordinator = RecoveryCoordinator(state_dir, "install-1")

    report = coordinator.prepare_resume("run_1")

    assert report.classification is RecoveryClassification.RESUMABLE_APPROVAL
    assert "resume" in report.allowed_actions


def test_prepare_resume_missing_run_is_not_resumable(tmp_path: Path) -> None:
    coordinator = RecoveryCoordinator(tmp_path / "state", "install-1")
    report = coordinator.prepare_resume("missing")
    assert report.classification is RecoveryClassification.MANUAL_REQUIRED
    assert "resume" not in report.allowed_actions


def test_resumer_hydrates_changeset_approval(tmp_path: Path) -> None:
    state_dir = _seed_approval_run(tmp_path)
    coordinator = RecoveryCoordinator(state_dir, "install-1")
    context = RunResumer(coordinator).load_context("run_1")
    assert context.run_id == "run_1"
    assert context.machine.state is RunState.AWAITING_APPROVAL
    assert context.messages == []


def test_resumer_rejects_non_resumable_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("before\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    journal = EventJournal(state_dir, "run_1", Redactor([]))
    journal.append(
        "run.started",
        {
            "goal": "edit",
            "workspace_root": str(workspace),
            "model_profile": "fake",
            "kind": "task",
        },
    )
    RecoverySnapshotStore(state_dir).save(
        make_snapshot(
            workspace,
            stage=RecoveryStage.STARTED,
            pending=False,
            files=(),
        )
    )
    coordinator = RecoveryCoordinator(state_dir, "install-1")
    with pytest.raises(ResumeRejected, match="safe_to_abandon"):
        RunResumer(coordinator).load_context("run_1")
