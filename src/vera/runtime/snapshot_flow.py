"""Stable event and recovery snapshot coordination for the runtime façade."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from vera import __version__
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.persistence.recovery_snapshot import RecoverySnapshotError
from vera.recovery.models import PersistedChangeSet, RecoverySnapshot
from vera.recovery.probe import workspace_identity
from vera.runtime.context import RunContext
from vera.runtime.flow_protocols import SnapshotFlowHost
from vera.runtime.intake import SnapshotPersistError
from vera.runtime.state import RunState


class SnapshotFlow:
    """Keep snapshot details out of the main runtime orchestration façade."""

    @staticmethod
    def snapshot_from_context(
        host: SnapshotFlowHost,
        context: RunContext,
        stage: RecoveryStage,
        sequence: int,
        *,
        verification_in_flight: bool,
    ) -> RecoverySnapshot:
        now = datetime.now(UTC)
        created_at = context.snapshot_created_at or now
        built = None
        if context.built_change_set is not None:
            built = PersistedChangeSet.from_built(context.built_change_set)
        checkpoint_id = None
        if context.checkpoint_manifest is not None:
            checkpoint_id = context.checkpoint_manifest.checkpoint_id
        return RecoverySnapshot(
            run_id=context.run_id,
            workspace_root=context.command.workspace_root,
            workspace_identity=workspace_identity(
                context.command.workspace_root, host.installation_id
            ),
            command=context.command,
            stage=stage,
            last_event_sequence=sequence,
            built_changeset=built,
            pending_tool_action=context.pending_tool_action,
            pending_git_operation=context.pending_git_operation,
            applied_file_mutations=tuple(context.applied_file_mutations),
            checkpoint_id=checkpoint_id,
            pending_approval=context.approval_gate.pending_approval,
            verification_index=context.verification_index,
            verification_failed=context.verification_failed,
            verification_in_flight=verification_in_flight,
            process_in_flight=context.process_in_flight,
            workspace_write_started=context.workspace_write_started,
            recovery_plan=context.pending_recovery_plan,
            security_findings=context.security_findings,
            security_context_hash=context.security_context_hash,
            created_at=created_at,
            updated_at=now,
            vera_version=__version__,
        )

    @staticmethod
    def stable_event(
        host: SnapshotFlowHost,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope:
        if not host._should_snapshot(context):
            return host._event(context, event_type, payload)
        event = context.journal.append(event_type, payload)
        snapshot = SnapshotFlow.snapshot_from_context(
            host,
            context,
            stage,
            event.sequence,
            verification_in_flight=event_type == "verification.started",
        )
        try:
            host.snapshot_store.save(snapshot)
        except RecoverySnapshotError as exc:
            with suppress(Exception):
                context.machine.transition(RunState.FAILED)
            failed = context.journal.append("run.failed", {"reason": "snapshot_write_failed"})
            raise SnapshotPersistError(failed) from exc
        if context.snapshot_created_at is None:
            context.snapshot_created_at = snapshot.created_at
        return event
