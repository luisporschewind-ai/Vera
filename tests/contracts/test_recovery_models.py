from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.changes import ChangeSet, FileChange
from vera.contracts.commands import CoreCommand, InspectRecovery, StartRun
from vera.contracts.recovery import (
    FileRecoveryState,
    RecoveryClassification,
    RecoveryEvidence,
    RecoveryReport,
    RecoveryStage,
)
from vera.recovery.models import PersistedChangeSet, RecoverySnapshot
from vera.workspace.changeset import sha256_bytes


def test_recovery_report_round_trips() -> None:
    report = RecoveryReport(
        run_id="run_1",
        classification=RecoveryClassification.RESUMABLE_APPROVAL,
        stage=RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        workspace_root=Path("/tmp/project"),
        evidence=(
            RecoveryEvidence(
                path="app.py",
                before_hash="a" * 64,
                after_hash="b" * 64,
                current_hash="a" * 64,
                state=FileRecoveryState.BEFORE,
            ),
        ),
        allowed_actions=("resume", "abandon"),
        reason_code="awaiting_changeset_approval",
    )
    assert RecoveryReport.model_validate_json(report.model_dump_json()) == report


def test_inspect_recovery_is_a_core_command() -> None:
    command: CoreCommand = InspectRecovery(run_id="run_1")
    assert command.schema_version == 1


def test_inspect_recovery_allows_scan_all() -> None:
    command = InspectRecovery()
    assert command.run_id is None
    assert InspectRecovery.model_validate_json(command.model_dump_json()) == command


def test_persisted_changeset_round_trips_and_checks_after_hash() -> None:
    after = b"print('ok')\n"
    after_hash = sha256_bytes(after)
    persisted = PersistedChangeSet(
        change_set=ChangeSet(
            changeset_id="cs_1",
            run_id="run_1",
            summary="edit",
            files=(
                FileChange(
                    operation="update",
                    path="app.py",
                    before_hash="a" * 64,
                    after_hash=after_hash,
                    unified_diff="@@ -1 +1 @@\n",
                ),
            ),
            verification=(),
            content_hash="c" * 64,
        ),
        intended_content_b64={"app.py": PersistedChangeSet.encode_bytes(after)},
    )

    restored = PersistedChangeSet.model_validate_json(persisted.model_dump_json())
    assert restored == persisted
    assert restored.decoded_content()["app.py"] == after


def test_recovery_snapshot_round_trips() -> None:
    snapshot = RecoverySnapshot(
        run_id="run_1",
        workspace_root=Path("/tmp/project"),
        workspace_identity="d" * 64,
        command=StartRun(goal="edit", workspace_root=Path("/tmp/project"), model_profile="fake"),
        stage=RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        last_event_sequence=4,
        pending_approval=ApprovalRequest(
            approval_id="approval_1",
            run_id="run_1",
            kind="changeset",
            target_id="cs_1",
            target_hash="hash",
            description="review",
            risk="medium",
        ),
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
        updated_at=datetime(2026, 9, 11, tzinfo=UTC),
        vera_version="0.1.0",
    )
    assert RecoverySnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert snapshot.snapshot_version == 1
