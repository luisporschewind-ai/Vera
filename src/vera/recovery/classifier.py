"""Pure recovery classification from snapshot facts and file evidence."""

from __future__ import annotations

from vera.contracts.recovery import (
    FileRecoveryState,
    RecoveryClassification,
    RecoveryEvidence,
    RecoveryReport,
    RecoveryStage,
)
from vera.recovery.models import RecoverySnapshot

_ACTIONS: dict[RecoveryClassification, tuple[str, ...]] = {
    RecoveryClassification.RESUMABLE_APPROVAL: ("inspect", "resume", "abandon"),
    RecoveryClassification.SAFE_TO_ABANDON: ("abandon", "rerun"),
    RecoveryClassification.RESUMABLE_VERIFICATION: ("inspect", "resume"),
    RecoveryClassification.RECOVERABLE_PARTIAL_APPLY: ("inspect", "restore"),
    RecoveryClassification.MANUAL_REQUIRED: ("inspect",),
    RecoveryClassification.LEGACY_NOT_RESUMABLE: ("inspect", "rollback"),
}

_CHECKPOINT_STAGES = frozenset(
    {
        RecoveryStage.CHECKPOINT_READY,
        RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
        RecoveryStage.VERIFYING,
    }
)
_VERIFICATION_STAGES = frozenset(
    {
        RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
        RecoveryStage.VERIFYING,
    }
)
_MANUAL = RecoveryClassification.MANUAL_REQUIRED


class RecoveryClassifier:
    def classify(
        self,
        snapshot: RecoverySnapshot,
        evidence: tuple[RecoveryEvidence, ...],
        *,
        identity_matches: bool = True,
        workspace_available: bool = True,
        checkpoint_available: bool | None = None,
    ) -> RecoveryReport:
        if not identity_matches:
            return self._report(snapshot, evidence, _MANUAL, "identity_mismatch")
        if not workspace_available:
            return self._report(snapshot, evidence, _MANUAL, "workspace_missing")
        if snapshot.verification_in_flight:
            return self._report(snapshot, evidence, _MANUAL, "verification_in_flight")

        expected = set()
        if snapshot.built_changeset is not None:
            expected = {item.path for item in snapshot.built_changeset.change_set.files}
        actual = {item.path for item in evidence}
        if expected != actual:
            return self._report(snapshot, evidence, _MANUAL, "evidence_conflict")

        if any(item.state is FileRecoveryState.UNKNOWN for item in evidence):
            return self._report(snapshot, evidence, _MANUAL, "unknown_hash")

        needs_checkpoint = snapshot.stage in _CHECKPOINT_STAGES or snapshot.workspace_write_started
        missing_checkpoint = snapshot.checkpoint_id is None or checkpoint_available is False
        if needs_checkpoint and missing_checkpoint:
            return self._report(snapshot, evidence, _MANUAL, "checkpoint_missing")

        states = {item.state for item in evidence}
        all_before = bool(evidence) and states <= {FileRecoveryState.BEFORE}
        all_after = bool(evidence) and states <= {FileRecoveryState.AFTER}
        mixed = FileRecoveryState.BEFORE in states and FileRecoveryState.AFTER in states

        if snapshot.stage is RecoveryStage.STARTED and not evidence:
            return self._report(
                snapshot,
                evidence,
                RecoveryClassification.SAFE_TO_ABANDON,
                "safe_to_abandon",
            )

        awaiting_approval = snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL
        if (
            awaiting_approval
            and all_before
            and snapshot.pending_approval is not None
            and not snapshot.workspace_write_started
        ):
            return self._report(
                snapshot,
                evidence,
                RecoveryClassification.RESUMABLE_APPROVAL,
                "awaiting_changeset_approval",
            )

        if snapshot.stage in _VERIFICATION_STAGES and all_after:
            return self._report(
                snapshot,
                evidence,
                RecoveryClassification.RESUMABLE_VERIFICATION,
                "awaiting_verification",
            )

        if mixed and snapshot.checkpoint_id is not None and checkpoint_available is not False:
            return self._report(
                snapshot,
                evidence,
                RecoveryClassification.RECOVERABLE_PARTIAL_APPLY,
                "recoverable_partial_apply",
            )

        if all_before and not snapshot.workspace_write_started:
            return self._report(
                snapshot,
                evidence,
                RecoveryClassification.SAFE_TO_ABANDON,
                "safe_to_abandon",
            )

        return self._report(snapshot, evidence, _MANUAL, "manual_required")

    @staticmethod
    def _report(
        snapshot: RecoverySnapshot,
        evidence: tuple[RecoveryEvidence, ...],
        classification: RecoveryClassification,
        reason_code: str,
    ) -> RecoveryReport:
        return RecoveryReport(
            run_id=snapshot.run_id,
            classification=classification,
            stage=snapshot.stage,
            workspace_root=snapshot.workspace_root,
            evidence=evidence,
            allowed_actions=_ACTIONS[classification],
            reason_code=reason_code,
        )
