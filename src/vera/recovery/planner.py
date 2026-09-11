"""Build an immutable partial-restore plan from classified evidence."""

from __future__ import annotations

from uuid import uuid4

from vera.contracts.recovery import (
    FileRecoveryState,
    RecoveryClassification,
    RecoveryPlan,
    RecoveryPlanFile,
    RecoveryReport,
)
from vera.recovery.models import RecoverySnapshot


class RecoveryPlanError(ValueError):
    """Raised when a recovery plan cannot be created from current evidence."""


class RecoveryPlanner:
    def plan(self, report: RecoveryReport, snapshot: RecoverySnapshot) -> RecoveryPlan:
        if any(item.state is FileRecoveryState.UNKNOWN for item in report.evidence):
            raise RecoveryPlanError("unknown_hash")
        if report.classification is not RecoveryClassification.RECOVERABLE_PARTIAL_APPLY:
            raise RecoveryPlanError(report.reason_code)
        if snapshot.built_changeset is None:
            raise RecoveryPlanError("missing_changeset")
        files = tuple(
            RecoveryPlanFile(
                path=item.path,
                before_hash=item.before_hash,
                after_hash=item.after_hash,
                current_hash=item.current_hash,
                action=(
                    "keep_before" if item.state is FileRecoveryState.BEFORE else "restore_before"
                ),
            )
            for item in report.evidence
        )
        return RecoveryPlan.create(
            recovery_id=f"recovery_{uuid4().hex}",
            run_id=report.run_id,
            workspace_identity=snapshot.workspace_identity,
            files=files,
        )
