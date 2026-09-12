"""Rebuild a paused RunContext from durable recovery facts."""

from __future__ import annotations

from vera.contracts.recovery import RecoveryStage
from vera.persistence.journal import EventJournal
from vera.recovery.models import RecoverySnapshot
from vera.runtime.approval import ApprovalGate
from vera.runtime.context import RunContext
from vera.runtime.security import current_security_hash
from vera.runtime.state import RunState, RunStateMachine
from vera.workspace.checkpoint import CheckpointStore

_APPROVAL_STAGES = frozenset(
    {
        RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        RecoveryStage.CHECKPOINT_READY,
    }
)
_VERIFICATION_STAGES = frozenset(
    {
        RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
        RecoveryStage.VERIFYING,
    }
)


class RecoveryHydrationError(ValueError):
    """Raised when a snapshot cannot be safely turned into a RunContext."""


class RecoveryHydrator:
    def hydrate(self, snapshot: RecoverySnapshot, journal: EventJournal) -> RunContext:
        if snapshot.verification_in_flight:
            raise RecoveryHydrationError("verification_in_flight")
        if snapshot.rollback_in_flight:
            raise RecoveryHydrationError("rollback_in_flight")
        events = journal.read_all()
        last_sequence = events[-1].sequence if events else 0
        if snapshot.last_event_sequence != last_sequence:
            raise RecoveryHydrationError("journal_sequence_mismatch")
        if snapshot.stage in _APPROVAL_STAGES:
            state = RunState.AWAITING_APPROVAL
        elif snapshot.stage in _VERIFICATION_STAGES:
            state = RunState.VERIFYING
        else:
            raise RecoveryHydrationError("unsupported_stage")
        checkpoint_manifest = None
        if snapshot.checkpoint_id is not None:
            try:
                checkpoint_manifest = CheckpointStore.load_manifest(
                    journal.state_dir, snapshot.run_id
                )
            except (OSError, ValueError) as exc:
                raise RecoveryHydrationError("checkpoint_missing") from exc
        built = None
        if snapshot.built_changeset is not None:
            built = snapshot.built_changeset.to_built()
        pending_command = None
        if (
            snapshot.stage is RecoveryStage.AWAITING_VERIFICATION_APPROVAL
            and built is not None
            and 0 <= snapshot.verification_index < len(built.change_set.verification)
        ):
            pending_command = built.change_set.verification[snapshot.verification_index]
        if snapshot.pending_approval is not None:
            approval_gate = ApprovalGate.restore(snapshot.pending_approval)
        else:
            approval_gate = ApprovalGate(snapshot.run_id)
        return RunContext(
            run_id=snapshot.run_id,
            command=snapshot.command,
            machine=RunStateMachine(state),
            journal=journal,
            messages=[],
            approval_gate=approval_gate,
            built_change_set=built,
            pending_command=pending_command,
            verification_index=snapshot.verification_index,
            verification_failed=snapshot.verification_failed,
            checkpoint_manifest=checkpoint_manifest,
            workspace_write_started=snapshot.workspace_write_started,
            snapshot_created_at=snapshot.created_at,
            pending_recovery_plan=snapshot.recovery_plan,
            security_findings=snapshot.security_findings,
            security_context_hash=current_security_hash(snapshot.security_findings),
        )
