"""Recovery, rollback, and state-inspection flows."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import (
    AbandonRun,
    ApplyStateMigration,
    InspectRecovery,
    InspectState,
    PlanStateMigration,
    ResumeRun,
    RollbackRun,
)
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification, RecoveryReport, RecoveryStage
from vera.persistence.journal import EventJournal
from vera.persistence.migration import StateMigrationService
from vera.persistence.recovery_snapshot import RecoverySnapshotError
from vera.persistence.run_store import RunStore
from vera.recovery.hydrator import RecoveryHydrationError, RecoveryHydrator
from vera.recovery.planner import RecoveryPlanError, RecoveryPlanner
from vera.recovery.resume import ResumeRejected, RunResumer
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.flow_protocols import RecoveryFlowHost
from vera.runtime.state import RunState, RunStateMachine
from vera.sandbox.files import PermissionPaths
from vera.workspace.apply import ChangeApplier, RollbackStatus
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


def rollback(host: RecoveryFlowHost, command: RollbackRun) -> Iterator[EventEnvelope]:
    context = host.runs.get(command.run_id or "")
    if context is None and command.checkpoint_id is not None:
        for candidate in host.runs.values():
            if candidate.built_change_set is not None and (
                f"checkpoint_{candidate.built_change_set.change_set.changeset_id}"
                == command.checkpoint_id
            ):
                context = candidate
                break
    if context is not None:
        run_id = context.run_id
        manifest = CheckpointStore.load_manifest(host.state_dir, run_id)
        journal = context.journal
    elif command.run_id is not None:
        run_id = command.run_id
        try:
            manifest = CheckpointStore.load_manifest(host.state_dir, run_id)
        except (OSError, ValueError):
            return
        journal = EventJournal(host.state_dir, run_id, Redactor([]))
    else:
        return
    paths = (
        PermissionPaths(host.access_session)
        if host.access_session is not None
        else WorkspacePaths(manifest.workspace_root)
    )
    result = ChangeApplier(paths, CheckpointStore(host.state_dir, paths)).rollback(manifest)
    if result.status is RollbackStatus.ROLLED_BACK:
        yield journal.append("rollback.completed", {"paths": list(result.paths)})
    else:
        yield journal.append(
            "rollback.conflicted",
            {"status": result.status.value, "paths": list(result.paths)},
        )


def report_payload(host: RecoveryFlowHost, report: RecoveryReport) -> dict[str, Any]:
    return {
        "run_id": report.run_id,
        "classification": report.classification.value,
        "stage": report.stage.value,
        "workspace_root": str(report.workspace_root),
        "allowed_actions": list(report.allowed_actions),
        "reason_code": report.reason_code,
        "evidence": [
            {
                "path": item.path,
                "before_hash": item.before_hash,
                "after_hash": item.after_hash,
                "current_hash": item.current_hash,
                "state": item.state.value,
            }
            for item in report.evidence
        ],
    }


def ephemeral_event(
    host: RecoveryFlowHost,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
    sequence: int = 1,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=str(uuid4()),
        run_id=run_id,
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload,
    )


def inspect_recovery(host: RecoveryFlowHost, command: InspectRecovery) -> Iterator[EventEnvelope]:
    reports = host.coordinator.scan(command.run_id)
    for sequence, report in enumerate(reports, start=1):
        yield host._ephemeral_event(
            report.run_id, "recovery.detected", host._report_payload(report), sequence
        )


def inspect_state(host: RecoveryFlowHost, command: InspectState) -> Iterator[EventEnvelope]:
    store = RunStore(host.state_dir)
    run_ids = (command.run_id,) if command.run_id else store.iter_run_ids()
    sequence = 1
    for run_id in run_ids:
        if run_id is None:
            continue
        status = store.format_status(run_id)
        yield host._ephemeral_event(
            run_id,
            "state.inspected",
            {"run_id": run_id, "format_status": status.value},
            sequence,
        )
        sequence += 1


def plan_state_migration(
    host: RecoveryFlowHost, command: PlanStateMigration
) -> Iterator[EventEnvelope]:
    service = StateMigrationService(host.state_dir)
    try:
        plan = service.plan(command.run_id)
    except Exception as exc:
        yield host._ephemeral_event(
            command.run_id,
            "state.migration_failed",
            {"run_id": command.run_id, "reason_code": str(exc)},
            1,
        )
        return
    yield host._ephemeral_event(
        command.run_id,
        "state.migration_planned",
        {
            "run_id": plan.run_id,
            "migration_id": plan.migration_id,
            "migration_hash": plan.migration_hash,
            "from_status": plan.from_status.value,
            "actions": list(plan.actions),
        },
        1,
    )


def apply_state_migration(
    host: RecoveryFlowHost, command: ApplyStateMigration
) -> Iterator[EventEnvelope]:
    service = StateMigrationService(host.state_dir)
    try:
        expected = service.plan(command.run_id)
    except Exception as exc:
        yield host._ephemeral_event(
            command.run_id,
            "state.migration_failed",
            {"run_id": command.run_id, "reason_code": str(exc)},
            1,
        )
        return
    if expected.migration_hash != command.migration_hash:
        yield host._ephemeral_event(
            command.run_id,
            "state.migration_failed",
            {
                "run_id": command.run_id,
                "reason_code": "migration_hash_mismatch",
                "migration_id": command.migration_id,
            },
            1,
        )
        return
    apply_plan = expected.model_copy(update={"migration_id": command.migration_id})
    result = service.apply(apply_plan)
    event_type = (
        "state.migration_completed"
        if result.status in {"completed", "noop"}
        else "state.migration_failed"
    )
    yield host._ephemeral_event(
        command.run_id,
        event_type,
        {
            "run_id": result.run_id,
            "migration_id": result.migration_id,
            "status": result.status,
            "reason_code": result.reason_code,
        },
        1,
    )


def reject_resume(host: RecoveryFlowHost, report: RecoveryReport) -> Iterator[EventEnvelope]:
    sequence = 1
    if (
        report.classification is RecoveryClassification.MANUAL_REQUIRED
        and host.snapshot_store.exists(report.run_id)
    ):
        try:
            snapshot = host.snapshot_store.load(report.run_id)
        except (OSError, ValueError, RecoverySnapshotError):
            snapshot = None
        if snapshot is not None and snapshot.pending_approval is not None:
            yield host._ephemeral_event(
                report.run_id,
                "approval.invalidated",
                {
                    "approval_id": snapshot.pending_approval.approval_id,
                    "run_id": report.run_id,
                    "reason": report.reason_code,
                },
                sequence,
            )
            sequence += 1
    event_type = (
        "recovery.manual_required"
        if report.classification is RecoveryClassification.MANUAL_REQUIRED
        else "recovery.detected"
    )
    yield host._ephemeral_event(report.run_id, event_type, host._report_payload(report), sequence)


def resume(host: RecoveryFlowHost, command: ResumeRun) -> Iterator[EventEnvelope]:
    report = host.coordinator.prepare_resume(command.run_id)
    resumable = {
        RecoveryClassification.RESUMABLE_APPROVAL,
        RecoveryClassification.RESUMABLE_VERIFICATION,
        RecoveryClassification.RECOVERABLE_PARTIAL_APPLY,
    }
    if report.classification not in resumable:
        yield from host._reject_resume(report)
        return
    existing = host.runs.get(command.run_id)
    if existing is not None:
        yield host._ephemeral_event(
            report.run_id, "recovery.detected", host._report_payload(report)
        )
        if existing.approval_gate.pending_approval is not None:
            yield host._ephemeral_event(
                existing.run_id,
                "approval.required",
                host._approval_payload(existing.approval_gate.pending_approval, existing),
                2,
            )
        return
    try:
        context = RunResumer(host.coordinator).load_context(command.run_id)
    except (ResumeRejected, RecoveryHydrationError, RecoverySnapshotError, OSError, ValueError):
        yield from host._reject_resume(report)
        return
    host._bind_default_policy_to_workspace(context.command.workspace_root)
    host.runs[context.run_id] = context
    if report.classification is RecoveryClassification.RECOVERABLE_PARTIAL_APPLY:
        yield from host._propose_partial_restore(context, report)
        return
    stage = report.stage
    yield host._stable_event(
        context,
        "recovery.resume_started",
        {
            "run_id": context.run_id,
            "classification": report.classification.value,
        },
        stage,
    )
    if context.approval_gate.pending_approval is not None:
        yield host._stable_event(
            context,
            "approval.required",
            host._approval_payload(context.approval_gate.pending_approval, context),
            stage,
        )
        yield host._stable_event(
            context,
            "recovery.resumed",
            {"run_id": context.run_id},
            stage,
        )
        return
    yield host._stable_event(
        context,
        "recovery.resumed",
        {"run_id": context.run_id},
        stage,
    )
    yield from host._verify(context)


def propose_partial_restore(
    host: RecoveryFlowHost, context: RunContext, report: RecoveryReport
) -> Iterator[EventEnvelope]:
    snapshot = host.snapshot_store.load(context.run_id)
    try:
        plan = RecoveryPlanner().plan(report, snapshot)
    except RecoveryPlanError:
        yield from host._reject_resume(report)
        return
    current = context.pending_recovery_plan
    pending = context.approval_gate.pending_approval
    if current is None or current.recovery_hash != plan.recovery_hash:
        if pending is not None:
            yield host._stable_event(
                context,
                "approval.invalidated",
                {
                    "approval_id": pending.approval_id,
                    "run_id": context.run_id,
                    "reason": "recovery_hash_changed",
                },
                report.stage,
            )
            context.approval_gate.pending_approval = None
        context.pending_recovery_plan = plan
        context.approval_gate.require(
            ApprovalKind.RECOVERY,
            plan.recovery_id,
            plan.recovery_hash,
            "恢复部分应用的 Change Set",
            "high",
            workspace_identity=host._policy_binding(context.command.workspace_root)[0],
            policy_hash=host.policy_engine.policy_hash,
            **host._security_approval_kwargs(context),
        )
    else:
        context.pending_recovery_plan = current
    stage = report.stage
    yield host._stable_event(
        context,
        "recovery.resume_started",
        {
            "run_id": context.run_id,
            "classification": report.classification.value,
        },
        stage,
    )
    plan = context.pending_recovery_plan
    assert plan is not None
    pending = context.approval_gate.pending_approval
    assert pending is not None
    yield host._stable_event(
        context,
        "recovery.restore_proposed",
        {
            "recovery_id": plan.recovery_id,
            "run_id": plan.run_id,
            "recovery_hash": plan.recovery_hash,
            "files": [{"path": item.path, "action": item.action} for item in plan.files],
        },
        stage,
    )
    yield host._stable_event(
        context,
        "approval.required",
        host._approval_payload(pending, context),
        stage,
    )


def apply_recovery_plan(
    host: RecoveryFlowHost, context: RunContext, request: ApprovalRequest
) -> Iterator[EventEnvelope]:
    plan = context.pending_recovery_plan
    manifest = context.checkpoint_manifest
    if plan is None or manifest is None:
        yield from host._fail(context, "missing_recovery_plan")
        return
    report = host.coordinator.prepare_resume(context.run_id)
    try:
        snapshot = host.snapshot_store.load(context.run_id)
        recomputed = RecoveryPlanner().plan(report, snapshot)
    except (RecoveryPlanError, RecoverySnapshotError, OSError, ValueError):
        yield host._stable_event(
            context,
            "approval.invalidated",
            {
                "approval_id": request.approval_id,
                "run_id": context.run_id,
                "reason": report.reason_code,
            },
            RecoveryStage.CHECKPOINT_READY,
        )
        return
    if recomputed.recovery_hash != request.target_hash:
        yield host._stable_event(
            context,
            "approval.invalidated",
            {
                "approval_id": request.approval_id,
                "run_id": context.run_id,
                "reason": "recovery_hash_changed",
            },
            RecoveryStage.CHECKPOINT_READY,
        )
        return
    paths = (
        PermissionPaths(host.access_session)
        if host.access_session is not None
        else WorkspacePaths(context.command.workspace_root)
    )
    result = ChangeApplier(
        paths,
        CheckpointStore(host.state_dir, paths),
        writer=host.file_writer,
    ).restore_partial(plan, manifest)
    if result.status is not RollbackStatus.ROLLED_BACK:
        with suppress(Exception):
            context.machine.transition(RunState.RECOVERY_REQUIRED)
        yield host._stable_event(
            context,
            "recovery.manual_required",
            {
                "run_id": context.run_id,
                "reason": result.error or result.status.value,
            },
            RecoveryStage.CHECKPOINT_READY,
        )
        return
    context.pending_recovery_plan = None
    with suppress(Exception):
        context.machine.transition(RunState.COMPLETED)
    yield host._stable_event(
        context,
        "recovery.restored",
        {"run_id": context.run_id, "paths": list(result.paths)},
        RecoveryStage.TERMINAL,
    )
    yield host._stable_event(
        context,
        "run.completed",
        {"state": "completed", "outcome": "restored"},
        RecoveryStage.TERMINAL,
    )


def context_from_snapshot(host: RecoveryFlowHost, run_id: str) -> RunContext:
    snapshot = host.snapshot_store.load(run_id)
    journal = EventJournal(host.state_dir, run_id, Redactor([]))
    try:
        return host._restore_skill_snapshot(RecoveryHydrator().hydrate(snapshot, journal), snapshot)
    except RecoveryHydrationError:
        context = RunContext(
            run_id=snapshot.run_id,
            command=snapshot.command,
            machine=RunStateMachine(),
            journal=journal,
            messages=[],
            approval_gate=ApprovalGate(snapshot.run_id),
            built_change_set=(
                snapshot.built_changeset.to_built()
                if snapshot.built_changeset is not None
                else None
            ),
            snapshot_created_at=snapshot.created_at,
        )
        return host._restore_skill_snapshot(context, snapshot)


def abandon(host: RecoveryFlowHost, command: AbandonRun) -> Iterator[EventEnvelope]:
    report = host.coordinator.prepare_resume(command.run_id)
    if "abandon" not in report.allowed_actions:
        yield host._ephemeral_event(
            report.run_id,
            "recovery.manual_required",
            host._report_payload(report),
        )
        return
    context = host.runs.get(command.run_id)
    if context is None:
        try:
            context = host._context_from_snapshot(command.run_id)
        except (RecoverySnapshotError, OSError, ValueError):
            yield from host._reject_resume(report)
            return
        host.runs[context.run_id] = context
    with suppress(Exception):
        context.machine.transition(RunState.CANCELLED)
    yield host._stable_event(
        context,
        "recovery.abandoned",
        {
            "run_id": context.run_id,
            "classification": report.classification.value,
        },
        RecoveryStage.TERMINAL,
    )


class RecoveryFlow:
    """Stable façade for rollback and recovery commands."""

    rollback = staticmethod(rollback)
    report_payload = staticmethod(report_payload)
    ephemeral_event = staticmethod(ephemeral_event)
    inspect_recovery = staticmethod(inspect_recovery)
    inspect_state = staticmethod(inspect_state)
    plan_state_migration = staticmethod(plan_state_migration)
    apply_state_migration = staticmethod(apply_state_migration)
    reject_resume = staticmethod(reject_resume)
    resume = staticmethod(resume)
    propose_partial_restore = staticmethod(propose_partial_restore)
    apply_recovery_plan = staticmethod(apply_recovery_plan)
    context_from_snapshot = staticmethod(context_from_snapshot)
    abandon = staticmethod(abandon)
