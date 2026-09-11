from pathlib import Path

import pytest

from tests.recovery.helpers import PartialRecoveryFixture
from vera.contracts.recovery import FileRecoveryState, RecoveryClassification
from vera.recovery.planner import RecoveryPlanError, RecoveryPlanner


def test_plan_keeps_before_and_restores_after(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    assert fixture.report.classification is RecoveryClassification.RECOVERABLE_PARTIAL_APPLY

    plan = RecoveryPlanner().plan(fixture.report, fixture.snapshot)

    by_path = {item.path: item for item in plan.files}
    assert by_path["keep.txt"].action == "keep_before"
    assert by_path["restore.txt"].action == "restore_before"
    assert plan.recovery_hash == type(plan).compute_hash(plan.workspace_identity, plan.files)


def test_plan_refuses_unknown_evidence(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    fixture.after_file.write_text("tampered\n", encoding="utf-8")
    from vera.recovery.classifier import RecoveryClassifier
    from vera.recovery.probe import WorkspaceEvidenceProbe

    evidence = WorkspaceEvidenceProbe(fixture.installation_id).inspect(fixture.snapshot)
    report = RecoveryClassifier().classify(
        fixture.snapshot,
        evidence,
        identity_matches=True,
        workspace_available=True,
        checkpoint_available=True,
    )
    assert any(item.state is FileRecoveryState.UNKNOWN for item in report.evidence)
    with pytest.raises(RecoveryPlanError, match="unknown_hash"):
        RecoveryPlanner().plan(report, fixture.snapshot)
