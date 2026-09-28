"""Core command dispatch flow."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from uuid import uuid4

from vera.content.envelope import EMPTY_SECURITY_CONTEXT_HASH, build_content_envelope
from vera.contracts.commands import (
    AbandonRun,
    ApplyStateMigration,
    CancelRun,
    CoreCommand,
    InspectRecovery,
    InspectState,
    PlanStateMigration,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.journal import EventJournal
from vera.persistence.operation_receipt import receipt_key
from vera.recovery.resume import RunResumer
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.flow_protocols import CommandFlowHost
from vera.runtime.state import RunState, RunStateMachine
from vera.skills.context import SkillContextError
from vera.skills.snapshot_store import SkillSnapshotError


def dispatch(host: CommandFlowHost, command: CoreCommand) -> Iterator[RuntimeOutput]:
    if isinstance(command, CancelRun):

        def _cancel_once() -> Iterator[EventEnvelope]:
            context = host.runs.get(command.run_id)
            if context is None:
                return
            pending = context.approval_gate.pending_approval
            if pending is not None and pending.kind == ApprovalKind.RECOVERY.value:
                host.runs.pop(command.run_id, None)
                return
            with suppress(Exception):
                context.machine.transition(RunState.CANCELLED)
            yield host._stable_event(
                context,
                "run.cancelled",
                {"reason": "cancelled_by_user"},
                RecoveryStage.TERMINAL,
            )

        yield from host._with_receipt(
            "cancel",
            command.run_id,
            {"run_id": command.run_id},
            _cancel_once(),
        )
        return
    if isinstance(command, ResolveApproval):
        yield from host._with_receipt(
            "resolve_approval",
            command.run_id,
            {
                "run_id": command.run_id,
                "approval_id": command.approval_id,
                "target_hash": command.target_hash,
                "decision": command.decision,
            },
            host._resolve_approval(command),
            extra_refs=lambda: host._file_effect_refs(command.run_id),
        )
        return
    if isinstance(command, RollbackRun):
        if command.run_id is None:
            yield from host._rollback(command)
            return
        rollback_run_id = command.run_id
        yield from host._with_receipt(
            "rollback",
            rollback_run_id,
            {"run_id": rollback_run_id, "checkpoint_id": command.checkpoint_id},
            host._rollback(command),
            extra_refs=lambda: host._file_effect_refs(rollback_run_id),
        )
        return
    if isinstance(command, InspectRecovery):
        yield from host._inspect_recovery(command)
        return
    if isinstance(command, InspectState):
        yield from host._inspect_state(command)
        return
    if isinstance(command, PlanStateMigration):
        yield from host._plan_state_migration(command)
        return
    if isinstance(command, ApplyStateMigration):
        yield from host._apply_state_migration(command)
        return
    if isinstance(command, ResumeRun):
        payload = {"run_id": command.run_id}
        operation_id, _input_hash = receipt_key("resume", payload)
        existing_receipt = host.receipts.load(command.run_id, operation_id)
        if existing_receipt is not None and command.run_id not in host.runs:
            with suppress(Exception):
                host.runs[command.run_id] = RunResumer(host.coordinator).load_context(
                    command.run_id
                )
        collected: list[EventEnvelope] = []
        for event in host._resume(command):
            collected.append(event)
            yield event
        if existing_receipt is None:
            host._commit_receipt(
                operation="resume",
                run_id=command.run_id,
                payload=payload,
                events=collected,
            )
        return
    if isinstance(command, AbandonRun):
        yield from host._abandon(command)
        return
    if not isinstance(command, StartRun):
        return
    run_id = f"run_{uuid4().hex}"
    kind = "compaction" if command.mode == "compact" else "task"
    host._bind_default_policy_to_workspace(command.workspace_root)
    goal_envelope = build_content_envelope(
        command.goal, source_kind="user_goal", origin="start_run.goal"
    )
    context = RunContext(
        run_id=run_id,
        command=command,
        machine=RunStateMachine(),
        journal=EventJournal(host.state_dir, run_id, Redactor([])),
        messages=[],
        approval_gate=ApprovalGate(run_id),
        security_context_hash=EMPTY_SECURITY_CONTEXT_HASH,
    )
    try:
        skill_bound = command.mode != "compact" and host._bind_skill_snapshot(context)
    except (SkillSnapshotError, SkillContextError) as exc:
        yield host._ephemeral_event(
            run_id,
            "run.failed",
            {"reason": getattr(exc, "code", "skill_snapshot_failed")},
        )
        return
    host.runs[run_id] = context
    context.machine.transition(RunState.DISCOVERING)
    yield host._stable_event(
        context,
        "run.started",
        {
            "run_id": run_id,
            "goal_hash": goal_envelope.content_hash,
            "goal_bytes": goal_envelope.byte_count,
            "workspace_root": str(command.workspace_root),
            "model_profile": command.model_profile,
            "kind": kind,
        },
        RecoveryStage.STARTED,
    )
    if skill_bound and context.skill_snapshot is not None:
        yield host._stable_event(
            context,
            "skill.snapshot.bound",
            {
                "snapshot_id": context.skill_snapshot.snapshot_id,
                "skill_id": context.skill_snapshot.skill_id,
                "source_kind": context.skill_snapshot.source_kind,
                "version": context.skill_snapshot.version,
                "manifest_hash": context.skill_snapshot.manifest_hash,
                "resource_hash": context.skill_snapshot.resource_hash,
            },
            RecoveryStage.STARTED,
        )
    yield from host._seed_context(context)
    if command.mode == "compact":
        yield from host._compact(context)
        return
    yield from host._drive(context)


class CommandFlow:
    """Stable façade for structured Core command dispatch."""

    dispatch = staticmethod(dispatch)
