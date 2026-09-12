"""Explicit recovery and rollback evaluation scenarios."""

from __future__ import annotations

from pathlib import Path

from vera.cli_driver import ApprovalDecision
from vera.contracts.commands import (
    CancelRun,
    InspectRecovery,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope
from vera.evals.contracts import EvalScenario, FileFact
from vera.evals.corpus import LoadedEvalCase
from vera.evals.failpoints import EvalFailpoint
from vera.evals.files import FileInventory
from vera.evals.isolation import IsolatedEvalCase
from vera.evals.runtime_factory import EvalRuntimeFactory
from vera.evals.script_driver import EvalExecution, EvalExecutionError
from vera.persistence.journal import EventJournal
from vera.redaction import Redactor
from vera.runtime.engine import VeraRuntime
from vera.workspace.apply import SimulatedCrash

_SIDE_EFFECT_EVENTS = (
    "changeset.applied",
    "rollback.completed",
    "verification.completed",
    "recovery.restored",
)

_FAILPOINTS: dict[EvalScenario, EvalFailpoint] = {
    EvalScenario.RESUME_AFTER_APPROVAL: EvalFailpoint.AWAITING_CHANGESET_APPROVAL,
    EvalScenario.IDEMPOTENT_RESUME: EvalFailpoint.AWAITING_CHANGESET_APPROVAL,
    EvalScenario.RESTORE_PARTIAL_APPLY: EvalFailpoint.AFTER_FIRST_WRITE,
    EvalScenario.IN_FLIGHT_MANUAL: EvalFailpoint.VERIFICATION_IN_FLIGHT,
}

_EXPECTED_CLASSIFICATION: dict[EvalScenario, str] = {
    EvalScenario.RESUME_AFTER_APPROVAL: "resumable_approval",
    EvalScenario.IDEMPOTENT_RESUME: "resumable_approval",
    EvalScenario.RESTORE_PARTIAL_APPLY: "recoverable_partial_apply",
    EvalScenario.IN_FLIGHT_MANUAL: "manual_required",
}


class RecoveryScenarioRunner:
    def execute(self, loaded: LoadedEvalCase, isolated: IsolatedEvalCase) -> EvalExecution:
        scenario = loaded.case.scenario
        failpoint = _FAILPOINTS.get(scenario)
        if failpoint is None:
            raise EvalExecutionError(
                "unsupported_scenario",
                f"no recovery failpoint for {scenario.value}",
            )
        factory = EvalRuntimeFactory()
        before = FileInventory.capture(isolated.workspace)
        runtime = factory.create(loaded, isolated, failpoint=failpoint)
        approvals = list(loaded.script.approvals)
        run_id, first_events, approvals = _interrupt_first_runtime(
            runtime, loaded, isolated, approvals
        )
        del runtime
        second = factory.create(loaded, isolated, failpoint=None, consume_script=False)
        inspect = tuple(second.handle(InspectRecovery(run_id=run_id)))
        classification, allowed = _recovery_facts(inspect)
        expected = _EXPECTED_CLASSIFICATION[scenario]
        events = list(first_events)
        events.extend(inspect)
        restart_offset = len(first_events)
        if classification != expected:
            return _execution(
                events,
                before,
                FileInventory.capture(isolated.workspace),
                runtime_instance_count=2,
                restart_event_offset=restart_offset,
                classification=classification,
                allowed=allowed,
            )
        if scenario is EvalScenario.IN_FLIGHT_MANUAL:
            resumed = tuple(second.handle(ResumeRun(run_id=run_id)))
            events.extend(resumed)
            classification, allowed = _recovery_facts((*inspect, *resumed))
            del second
            return _execution(
                events,
                before,
                FileInventory.capture(isolated.workspace),
                runtime_instance_count=2,
                restart_event_offset=restart_offset,
                classification=classification,
                allowed=allowed,
            )
        first_resume = tuple(second.handle(ResumeRun(run_id=run_id)))
        events.extend(first_resume)
        if scenario is EvalScenario.IDEMPOTENT_RESUME:
            events.extend(second.handle(ResumeRun(run_id=run_id)))
        events.extend(_drain_approvals(second, first_resume, approvals))
        classification, allowed = _recovery_facts(tuple(events[restart_offset:]))
        del second
        return _execution(
            events,
            before,
            FileInventory.capture(isolated.workspace),
            runtime_instance_count=2,
            restart_event_offset=restart_offset,
            classification=classification or expected,
            allowed=allowed,
        )


class RollbackScenarioRunner:
    def execute(self, loaded: LoadedEvalCase, isolated: IsolatedEvalCase) -> EvalExecution:
        if loaded.case.scenario is not EvalScenario.ROLLBACK:
            raise EvalExecutionError("unsupported_scenario", "rollback runner expected rollback")
        factory = EvalRuntimeFactory()
        runtime = factory.create(loaded, isolated)
        before = FileInventory.capture(isolated.workspace)
        approvals = list(loaded.script.approvals)
        events = list(
            _drive_to_terminal(
                runtime,
                StartRun(
                    goal=loaded.case.goal,
                    workspace_root=isolated.workspace,
                    model_profile="fake",
                ),
                approvals,
            )
        )
        if approvals:
            raise EvalExecutionError("leftover_approvals", "approval script was not fully consumed")
        run_id = events[0].run_id
        events.extend(runtime.handle(RollbackRun(run_id=run_id)))
        del runtime
        return _execution(
            events,
            before,
            FileInventory.capture(isolated.workspace),
            runtime_instance_count=1,
            restart_event_offset=None,
            classification=None,
            allowed=(),
        )


def _interrupt_first_runtime(
    runtime: VeraRuntime,
    loaded: LoadedEvalCase,
    isolated: IsolatedEvalCase,
    approvals: list[ApprovalDecision],
) -> tuple[str, list[EventEnvelope], list[ApprovalDecision]]:
    events: list[EventEnvelope] = []
    command: StartRun | ResolveApproval | CancelRun = StartRun(
        goal=loaded.case.goal,
        workspace_root=isolated.workspace,
        model_profile="fake",
    )
    crashed = False
    while True:
        batch: list[EventEnvelope] = []
        try:
            for event in runtime.handle(command):
                batch.append(event)
        except SimulatedCrash:
            events.extend(batch)
            crashed = True
            break
        events.extend(batch)
        approval = _pending_approval(batch)
        if approval is None:
            break
        if not approvals:
            raise EvalExecutionError(
                "approval_script_exhausted",
                "no scripted approval remains for this boundary",
            )
        command = _approval_command(approval, approvals.pop(0))
    if not crashed:
        raise EvalExecutionError("failpoint_not_triggered", "failpoint did not interrupt the run")
    run_id = _run_id(events, runtime)
    journaled = _read_journal(isolated.state_dir, run_id)
    return run_id, list(journaled) if journaled else events, approvals


def _drive_to_terminal(
    runtime: VeraRuntime,
    start: StartRun,
    approvals: list[ApprovalDecision],
) -> list[EventEnvelope]:
    events: list[EventEnvelope] = []
    command: StartRun | ResolveApproval | CancelRun = start
    while True:
        batch = list(runtime.handle(command))
        events.extend(batch)
        approval = _pending_approval(batch)
        if approval is None:
            return events
        if not approvals:
            raise EvalExecutionError(
                "approval_script_exhausted",
                "no scripted approval remains for this boundary",
            )
        command = _approval_command(approval, approvals.pop(0))


def _drain_approvals(
    runtime: VeraRuntime,
    last_batch: tuple[EventEnvelope, ...],
    approvals: list[ApprovalDecision],
) -> list[EventEnvelope]:
    collected: list[EventEnvelope] = []
    batch: tuple[EventEnvelope, ...] = last_batch
    while True:
        approval = _pending_approval(batch)
        if approval is None:
            return collected
        if not approvals:
            raise EvalExecutionError(
                "approval_script_exhausted",
                "no scripted approval remains for this boundary",
            )
        batch = tuple(runtime.handle(_approval_command(approval, approvals.pop(0))))
        collected.extend(batch)


def _pending_approval(
    batch: list[EventEnvelope] | tuple[EventEnvelope, ...],
) -> EventEnvelope | None:
    return next((event for event in reversed(batch) if event.type == "approval.required"), None)


def _approval_command(
    approval: EventEnvelope, decision: ApprovalDecision
) -> ResolveApproval | CancelRun:
    if decision == "cancel":
        return CancelRun(run_id=approval.run_id)
    return ResolveApproval(
        run_id=approval.run_id,
        approval_id=str(approval.payload["approval_id"]),
        target_hash=str(approval.payload["target_hash"]),
        decision=decision,
    )


def _run_id(events: list[EventEnvelope], runtime: VeraRuntime) -> str:
    if events:
        return events[0].run_id
    if runtime.runs:
        return next(iter(runtime.runs))
    raise EvalExecutionError("missing_run_id", "failpoint interrupted before a run id existed")


def _read_journal(state_dir: Path, run_id: str) -> tuple[EventEnvelope, ...]:
    path = state_dir / "runs" / run_id / "events.jsonl"
    if not path.is_file():
        return ()
    return EventJournal(state_dir, run_id, Redactor([]), ensure_manifest=False).read_all()


def _recovery_facts(events: tuple[EventEnvelope, ...]) -> tuple[str | None, tuple[str, ...]]:
    classification: str | None = None
    allowed: tuple[str, ...] = ()
    for event in events:
        payload = event.payload
        raw = payload.get("classification")
        if isinstance(raw, str) and raw:
            classification = raw
        actions = payload.get("allowed_actions")
        if isinstance(actions, list):
            allowed = tuple(str(item) for item in actions)
    return classification, allowed


def _execution(
    events: list[EventEnvelope],
    before: tuple[FileFact, ...],
    after: tuple[FileFact, ...],
    *,
    runtime_instance_count: int,
    restart_event_offset: int | None,
    classification: str | None,
    allowed: tuple[str, ...],
) -> EvalExecution:
    run_ids = tuple(dict.fromkeys(event.run_id for event in events))
    counts = {
        name: sum(1 for event in events if event.type == name) for name in _SIDE_EFFECT_EVENTS
    }
    return EvalExecution(
        run_ids=run_ids,
        events=tuple(events),
        before_files=before,
        after_files=after,
        runtime_instance_count=runtime_instance_count,
        restart_event_offset=restart_event_offset,
        side_effect_counts=counts,
        recovery_classification=classification,
        allowed_actions=allowed,
    )
