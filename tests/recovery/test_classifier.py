from pathlib import Path

import pytest

from tests.recovery.helpers import make_snapshot
from vera.contracts.recovery import (
    FileRecoveryState,
    RecoveryClassification,
    RecoveryEvidence,
    RecoveryStage,
)
from vera.recovery.classifier import RecoveryClassifier


def _evidence(*states: FileRecoveryState) -> tuple[RecoveryEvidence, ...]:
    items: list[RecoveryEvidence] = []
    for index, state in enumerate(states):
        before = "b" * 64
        after = "a" * 64
        current = {
            FileRecoveryState.BEFORE: before,
            FileRecoveryState.AFTER: after,
            FileRecoveryState.UNKNOWN: "c" * 64,
        }[state]
        items.append(
            RecoveryEvidence(
                path=f"app{index}.py",
                before_hash=before,
                after_hash=after,
                current_hash=current,
                state=state,
            )
        )
    return tuple(items)


def _snapshot_for(
    tmp_path: Path,
    stage: RecoveryStage,
    evidence: tuple[RecoveryEvidence, ...],
    *,
    in_flight: bool = False,
    checkpoint: bool = False,
    identity: str | None = None,
) -> object:
    files = tuple((item.path, "update", b"before\n", b"after\n") for item in evidence)
    checkpoint_stages = {
        RecoveryStage.CHECKPOINT_READY,
        RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
        RecoveryStage.VERIFYING,
    }
    return make_snapshot(
        tmp_path,
        files=files,
        stage=stage,
        pending=stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        checkpoint_id="checkpoint_1" if checkpoint or stage in checkpoint_stages else None,
        verification_in_flight=in_flight,
        workspace_write_started=stage
        in {
            RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
            RecoveryStage.VERIFYING,
        },
        identity=identity,
    )


@pytest.mark.parametrize(
    ("stage", "states", "in_flight", "expected"),
    [
        (RecoveryStage.STARTED, (), False, RecoveryClassification.SAFE_TO_ABANDON),
        (
            RecoveryStage.AWAITING_CHANGESET_APPROVAL,
            (FileRecoveryState.BEFORE,),
            False,
            RecoveryClassification.RESUMABLE_APPROVAL,
        ),
        (
            RecoveryStage.VERIFYING,
            (FileRecoveryState.AFTER,),
            False,
            RecoveryClassification.RESUMABLE_VERIFICATION,
        ),
        (
            RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
            (FileRecoveryState.AFTER,),
            False,
            RecoveryClassification.RESUMABLE_VERIFICATION,
        ),
        (
            RecoveryStage.CHECKPOINT_READY,
            (FileRecoveryState.BEFORE, FileRecoveryState.AFTER),
            False,
            RecoveryClassification.RECOVERABLE_PARTIAL_APPLY,
        ),
        (
            RecoveryStage.VERIFYING,
            (FileRecoveryState.AFTER,),
            True,
            RecoveryClassification.MANUAL_REQUIRED,
        ),
        (
            RecoveryStage.AWAITING_CHANGESET_APPROVAL,
            (FileRecoveryState.UNKNOWN,),
            False,
            RecoveryClassification.MANUAL_REQUIRED,
        ),
    ],
)
def test_classifier_table(
    tmp_path: Path,
    stage: RecoveryStage,
    states: tuple[FileRecoveryState, ...],
    in_flight: bool,
    expected: RecoveryClassification,
) -> None:
    evidence = _evidence(*states)
    snapshot = _snapshot_for(tmp_path, stage, evidence, in_flight=in_flight)
    report = RecoveryClassifier().classify(snapshot, evidence)
    assert report.classification is expected
    assert report.run_id == "run_1"


def test_identity_mismatch_is_manual(tmp_path: Path) -> None:
    evidence = _evidence(FileRecoveryState.BEFORE)
    snapshot = _snapshot_for(
        tmp_path,
        RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        evidence,
        identity="0" * 64,
    )
    report = RecoveryClassifier().classify(snapshot, evidence, identity_matches=False)
    assert report.classification is RecoveryClassification.MANUAL_REQUIRED
    assert report.reason_code == "identity_mismatch"


def test_missing_workspace_is_manual(tmp_path: Path) -> None:
    evidence = _evidence(FileRecoveryState.UNKNOWN)
    snapshot = _snapshot_for(tmp_path, RecoveryStage.AWAITING_CHANGESET_APPROVAL, evidence)
    report = RecoveryClassifier().classify(snapshot, evidence, workspace_available=False)
    assert report.classification is RecoveryClassification.MANUAL_REQUIRED
    assert report.reason_code == "workspace_missing"


def test_path_set_conflict_is_manual(tmp_path: Path) -> None:
    evidence = _evidence(FileRecoveryState.BEFORE)
    snapshot = _snapshot_for(tmp_path, RecoveryStage.AWAITING_CHANGESET_APPROVAL, evidence)
    extra = evidence + (
        RecoveryEvidence(
            path="other.py",
            before_hash="b" * 64,
            after_hash="a" * 64,
            current_hash="b" * 64,
            state=FileRecoveryState.BEFORE,
        ),
    )
    report = RecoveryClassifier().classify(snapshot, extra)
    assert report.classification is RecoveryClassification.MANUAL_REQUIRED
    assert report.reason_code == "evidence_conflict"


def test_missing_checkpoint_is_manual(tmp_path: Path) -> None:
    evidence = _evidence(FileRecoveryState.BEFORE, FileRecoveryState.AFTER)
    snapshot = make_snapshot(
        tmp_path,
        files=(
            ("app0.py", "update", b"before\n", b"after\n"),
            ("app1.py", "update", b"before\n", b"after\n"),
        ),
        stage=RecoveryStage.CHECKPOINT_READY,
        pending=False,
        checkpoint_id=None,
        workspace_write_started=True,
    )
    report = RecoveryClassifier().classify(snapshot, evidence, checkpoint_available=False)
    assert report.classification is RecoveryClassification.MANUAL_REQUIRED
    assert report.reason_code == "checkpoint_missing"
