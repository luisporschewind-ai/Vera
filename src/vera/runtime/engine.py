"""Bounded discovery loop that stops before any filesystem mutation."""

from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel

from vera import __version__
from vera.config import Limits
from vera.contracts.approvals import ApprovalRequest
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
from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification, RecoveryReport, RecoveryStage
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelAdapter, ModelMessage, ModelRequest, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.persistence.migration import StateMigrationService
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.persistence.run_store import RunStore
from vera.policy.engine import PolicyEngine
from vera.policy.snapshot import EffectivePolicySnapshot
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.hydrator import RecoveryHydrationError, RecoveryHydrator
from vera.recovery.models import PersistedChangeSet, RecoverySnapshot
from vera.recovery.planner import RecoveryPlanError, RecoveryPlanner
from vera.recovery.probe import workspace_identity
from vera.recovery.resume import ResumeRejected, RunResumer
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.prompts import COMPACTION_PROMPT, SYSTEM_PROMPT
from vera.runtime.state import RunState, RunStateMachine
from vera.tools.command_policy import CommandDecisionKind, CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.verification.runner import VerificationRunner
from vera.workspace.apply import ApplyStatus, ChangeApplier, FileWriter, RollbackStatus
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


class SnapshotPersistError(RuntimeError):
    """Raised after a failed snapshot write so the Runtime can stop without looping."""

    def __init__(self, failed_event: EventEnvelope) -> None:
        super().__init__("snapshot_write_failed")
        self.failed_event = failed_event


class ProposalInput(BaseModel):
    summary: str
    changes: tuple[ChangeProposal, ...]
    verification: tuple[VerificationCommand, ...] = ()
    risk: str = "medium"


class VeraRuntime:
    def __init__(
        self,
        adapter: ModelAdapter,
        registry: ToolRegistry,
        state_dir: Path,
        limits: Limits | None = None,
        command_policy: CommandPolicy | None = None,
        *,
        snapshot_store: RecoverySnapshotStore | None = None,
        installation_id: str | None = None,
        recovery_coordinator: RecoveryCoordinator | None = None,
        file_writer: FileWriter | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.state_dir = state_dir
        self.limits = limits or Limits()
        self.installation_id = installation_id or "local"
        if policy_engine is not None:
            self.policy_engine = policy_engine
        elif command_policy is not None:
            self.policy_engine = command_policy.engine
        else:
            self.policy_engine = PolicyEngine(EffectivePolicySnapshot(workspace_identity="default"))
        self.command_policy = command_policy or CommandPolicy(
            self.policy_engine.snapshot.user_allowed_command_prefixes,
            policy_engine=self.policy_engine,
            workspace_identity=self.policy_engine.snapshot.workspace_identity,
        )
        self.runs: dict[str, RunContext] = {}
        self.snapshot_store = snapshot_store or RecoverySnapshotStore(state_dir)
        self.file_writer = file_writer
        self.coordinator = recovery_coordinator or RecoveryCoordinator(
            state_dir,
            self.installation_id,
            snapshot_store=self.snapshot_store,
        )

    def _policy_binding(self, root: Path) -> tuple[str, str]:
        identity = workspace_identity(root, self.installation_id)
        return identity, self.policy_engine.policy_hash

    def _approval_payload(
        self, request: ApprovalRequest, context: RunContext | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "approval_id": request.approval_id,
            "run_id": request.run_id,
            "kind": request.kind,
            "target_id": request.target_id,
            "target_hash": request.target_hash,
            "description": request.description,
            "risk": request.risk,
            "workspace_identity": request.workspace_identity,
            "policy_hash": request.policy_hash,
        }
        if (
            context is not None
            and request.kind == ApprovalKind.COMMAND.value
            and context.pending_command is not None
        ):
            payload["argv"] = list(context.pending_command.argv)
            payload["cwd"] = context.pending_command.cwd
        return payload

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope:
        return context.journal.append(event_type, payload)

    def _should_snapshot(self, context: RunContext) -> bool:
        return context.command.mode != "compact"

    def _snapshot_from_context(
        self,
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
                context.command.workspace_root, self.installation_id
            ),
            command=context.command,
            stage=stage,
            last_event_sequence=sequence,
            built_changeset=built,
            checkpoint_id=checkpoint_id,
            pending_approval=context.approval_gate.pending_approval,
            verification_index=context.verification_index,
            verification_failed=context.verification_failed,
            verification_in_flight=verification_in_flight,
            workspace_write_started=context.workspace_write_started,
            recovery_plan=context.pending_recovery_plan,
            created_at=created_at,
            updated_at=now,
            vera_version=__version__,
        )

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope:
        if not self._should_snapshot(context):
            return self._event(context, event_type, payload)
        event = context.journal.append(event_type, payload)
        snapshot = self._snapshot_from_context(
            context,
            stage,
            event.sequence,
            verification_in_flight=event_type == "verification.started",
        )
        try:
            self.snapshot_store.save(snapshot)
        except RecoverySnapshotError as exc:
            with suppress(Exception):
                context.machine.transition(RunState.FAILED)
            failed = context.journal.append("run.failed", {"reason": "snapshot_write_failed"})
            raise SnapshotPersistError(failed) from exc
        if context.snapshot_created_at is None:
            context.snapshot_created_at = snapshot.created_at
        return event

    def _definitions(self) -> tuple[dict[str, Any], ...]:
        definitions: list[dict[str, Any]] = []
        for name in self.registry.definitions():
            tool = self.registry.get(name)
            if tool is None:
                continue
            model = tool.input_model
            definitions.append(
                {
                    "name": name,
                    "description": getattr(tool, "description", name),
                    "input_schema": model.model_json_schema(),
                }
            )
        definitions.extend(
            [
                {
                    "name": "propose_changeset",
                    "description": "propose a reviewable set of file changes",
                    "input_schema": ProposalInput.model_json_schema(),
                }
            ]
        )
        return tuple(definitions)

    def _model_request(self, context: RunContext) -> ModelRequest:
        from vera.tools.definitions import ToolDefinition

        tools = tuple(ToolDefinition(**definition) for definition in self._definitions())
        return ModelRequest(
            messages=tuple(context.messages),
            tools=tools,
            max_output_tokens=4_096,
        )

    def _fail(self, context: RunContext, reason: str) -> Iterator[EventEnvelope]:
        with suppress(Exception):
            context.machine.transition(RunState.FAILED)
        yield self._stable_event(context, "run.failed", {"reason": reason}, RecoveryStage.TERMINAL)

    def _propose(self, context: RunContext, call: ModelToolCall) -> Iterator[EventEnvelope]:
        try:
            proposal = ProposalInput.model_validate(call.arguments)
            built = ChangeSetBuilder(WorkspacePaths(context.command.workspace_root)).build(
                context.run_id,
                proposal.summary,
                proposal.changes,
                proposal.verification,
            )
        except Exception as exc:
            yield self._event(
                context,
                "tool.completed",
                {"name": call.name, "ok": False, "error": str(exc)},
            )
            return
        context.built_change_set = built
        context.machine.transition(RunState.CHANGESET_PROPOSED)
        change_set = built.change_set
        yield self._event(
            context,
            "changeset.proposed",
            {
                "changeset_id": change_set.changeset_id,
                "content_hash": change_set.content_hash,
                "files": [
                    {
                        "path": item.path,
                        "operation": item.operation,
                        "before_hash": item.before_hash,
                        "after_hash": item.after_hash,
                        "unified_diff": item.unified_diff,
                    }
                    for item in change_set.files
                ],
            },
        )
        context.machine.transition(RunState.AWAITING_APPROVAL)
        risk = cast(
            Literal["low", "medium", "high"],
            proposal.risk if proposal.risk in {"low", "medium", "high"} else "medium",
        )
        request = context.approval_gate.require(
            ApprovalKind.CHANGESET,
            change_set.changeset_id,
            change_set.content_hash,
            change_set.summary,
            risk,
            workspace_identity=self._policy_binding(context.command.workspace_root)[0],
            policy_hash=self.policy_engine.policy_hash,
        )
        yield self._stable_event(
            context,
            "approval.required",
            self._approval_payload(request),
            RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        )

    def _verify(self, context: RunContext) -> Iterator[EventEnvelope]:
        built = context.built_change_set
        if built is None:
            yield from self._fail(context, "missing_changeset")
            return
        runner = VerificationRunner(context.command.workspace_root)
        policy = self.command_policy
        while context.verification_index < len(built.change_set.verification):
            index = context.verification_index
            command = built.change_set.verification[index]
            decision = policy.classify(command)
            if decision.kind is CommandDecisionKind.FORBIDDEN:
                context.verification_failed = True
                context.verification_index += 1
                yield self._stable_event(
                    context,
                    "verification.completed",
                    {"index": index, "status": "rejected", "reason": decision.reason},
                    RecoveryStage.VERIFYING,
                )
                continue
            if decision.kind is CommandDecisionKind.APPROVAL_REQUIRED:
                context.pending_command = command
                request = context.approval_gate.require(
                    ApprovalKind.COMMAND,
                    f"verification_{index}",
                    built.change_set.content_hash,
                    "执行验证命令",
                    "medium",
                    workspace_identity=self._policy_binding(context.command.workspace_root)[0],
                    policy_hash=self.policy_engine.policy_hash,
                )
                payload = self._approval_payload(request)
                payload.update({"argv": list(command.argv), "cwd": command.cwd})
                yield self._stable_event(
                    context,
                    "approval.required",
                    payload,
                    RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
                )
                return
            yield self._stable_event(
                context,
                "verification.started",
                {"index": index, "argv": list(command.argv), "cwd": command.cwd},
                RecoveryStage.VERIFYING,
            )
            result = runner.run(command)
            context.verification_failed = context.verification_failed or result.status != "passed"
            context.verification_index += 1
            yield self._stable_event(
                context,
                "verification.completed",
                {
                    "index": index,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "stdout_truncated": result.stdout_truncated,
                    "stderr_truncated": result.stderr_truncated,
                },
                RecoveryStage.VERIFYING,
            )
        terminal = (
            RunState.VERIFICATION_FAILED if context.verification_failed else RunState.COMPLETED
        )
        context.machine.transition(terminal)
        yield self._stable_event(
            context,
            "run.completed",
            {"state": context.machine.state.value},
            RecoveryStage.TERMINAL,
        )

    def _resolve_approval(self, command: ResolveApproval) -> Iterator[EventEnvelope]:
        context = self.runs.get(command.run_id)
        if context is None or context.approval_gate.pending_approval is None:
            return
        request = context.approval_gate.pending_approval
        identity, current_hash = self._policy_binding(context.command.workspace_root)
        if request.policy_hash is not None and request.policy_hash != current_hash:
            context.approval_gate.pending_approval = None
            yield self._stable_event(
                context,
                "approval.invalidated",
                {
                    "approval_id": request.approval_id,
                    "run_id": context.run_id,
                    "reason_code": "policy_changed",
                },
                RecoveryStage.AWAITING_CHANGESET_APPROVAL,
            )
            return
        if request.workspace_identity is not None and request.workspace_identity != identity:
            context.approval_gate.pending_approval = None
            yield self._stable_event(
                context,
                "approval.invalidated",
                {
                    "approval_id": request.approval_id,
                    "run_id": context.run_id,
                    "reason_code": "workspace_identity_changed",
                },
                RecoveryStage.AWAITING_CHANGESET_APPROVAL,
            )
            return
        try:
            decision = context.approval_gate.resolve(command)
        except Exception as exc:
            yield self._event(context, "run.failed", {"reason": str(exc)})
            return
        yield self._event(
            context,
            "approval.resolved",
            {"approval_id": request.approval_id, "decision": decision, "kind": request.kind},
        )
        if request.kind == ApprovalKind.COMMAND.value:
            if decision == "reject":
                context.verification_failed = True
                context.pending_command = None
                context.verification_index += 1
                yield self._stable_event(
                    context,
                    "verification.completed",
                    {"index": context.verification_index - 1, "status": "rejected"},
                    RecoveryStage.VERIFYING,
                )
            elif context.pending_command is not None:
                result = VerificationRunner(context.command.workspace_root).run(
                    context.pending_command
                )
                context.verification_failed = (
                    context.verification_failed or result.status != "passed"
                )
                context.pending_command = None
                context.verification_index += 1
                yield self._stable_event(
                    context,
                    "verification.completed",
                    {
                        "index": context.verification_index - 1,
                        "status": result.status,
                        "exit_code": result.exit_code,
                    },
                    RecoveryStage.VERIFYING,
                )
            yield from self._verify(context)
            return
        if request.kind == ApprovalKind.RECOVERY.value:
            if decision == "reject":
                context.pending_recovery_plan = None
                yield self._stable_event(
                    context,
                    "recovery.detected",
                    self._report_payload(self.coordinator.prepare_resume(context.run_id)),
                    RecoveryStage.CHECKPOINT_READY,
                )
                return
            yield from self._apply_recovery_plan(context, request)
            return
        if decision == "reject":
            context.machine.transition(RunState.CANCELLED)
            yield self._stable_event(
                context,
                "run.cancelled",
                {"reason": "approval_rejected"},
                RecoveryStage.TERMINAL,
            )
            return
        built = context.built_change_set
        if built is None:
            yield from self._fail(context, "missing_changeset")
            return
        paths = WorkspacePaths(context.command.workspace_root)
        store = CheckpointStore(self.state_dir, paths)
        applier = ChangeApplier(paths, store, writer=self.file_writer)
        try:
            context.machine.transition(RunState.CHECKPOINTING)
            manifest = store.create(built.change_set)
        except Exception as exc:
            yield from self._fail(context, f"checkpoint_failed:{exc}")
            return
        context.checkpoint_manifest = manifest
        yield self._stable_event(
            context,
            "checkpoint.created",
            {"checkpoint_id": manifest.checkpoint_id},
            RecoveryStage.CHECKPOINT_READY,
        )
        context.machine.transition(RunState.APPLYING)
        apply_result = applier.apply(built, manifest)
        if apply_result.status is not ApplyStatus.APPLIED:
            event_type = (
                "checkpoint.restored"
                if apply_result.status is ApplyStatus.RESTORED_AFTER_FAILURE
                else "checkpoint.restore_failed"
            )
            yield self._event(
                context,
                event_type,
                {"status": apply_result.status.value, "paths": list(apply_result.paths)},
            )
            yield from self._fail(context, apply_result.status.value)
            return
        context.workspace_write_started = True
        yield self._stable_event(
            context,
            "changeset.applied",
            {"status": apply_result.status.value},
            RecoveryStage.VERIFYING,
        )
        context.machine.transition(RunState.VERIFYING)
        yield from self._verify(context)

    def _rollback(self, command: RollbackRun) -> Iterator[EventEnvelope]:
        context = self.runs.get(command.run_id or "")
        if context is None and command.checkpoint_id is not None:
            for candidate in self.runs.values():
                if candidate.built_change_set is not None and (
                    f"checkpoint_{candidate.built_change_set.change_set.changeset_id}"
                    == command.checkpoint_id
                ):
                    context = candidate
                    break
        if context is not None:
            run_id = context.run_id
            manifest = CheckpointStore.load_manifest(self.state_dir, run_id)
            journal = context.journal
        elif command.run_id is not None:
            run_id = command.run_id
            try:
                manifest = CheckpointStore.load_manifest(self.state_dir, run_id)
            except (OSError, ValueError):
                return
            journal = EventJournal(self.state_dir, run_id, Redactor([]))
        else:
            return
        paths = WorkspacePaths(manifest.workspace_root)
        result = ChangeApplier(paths, CheckpointStore(self.state_dir, paths)).rollback(manifest)
        if result.status is RollbackStatus.ROLLED_BACK:
            yield journal.append("rollback.completed", {"paths": list(result.paths)})
        else:
            yield journal.append(
                "rollback.conflicted",
                {"status": result.status.value, "paths": list(result.paths)},
            )

    def _execute_tool(self, context: RunContext, call: ModelToolCall) -> Iterator[EventEnvelope]:
        key = f"{call.name}:{call.arguments}"
        context.repeated_calls[key] = context.repeated_calls.get(key, 0) + 1
        if context.repeated_calls[key] >= 3:
            yield from self._fail(context, "repeated_tool_call")
            return
        yield self._event(context, "tool.started", {"name": call.name, "call_id": call.call_id})
        if call.name == "propose_changeset":
            yield from self._propose(context, call)
            return
        result = self.registry.execute(call.name, call.arguments)
        payload = {
            "name": call.name,
            "call_id": call.call_id,
            "ok": result.ok,
            "truncated": result.truncated,
            "error_code": result.error_code,
        }
        yield self._event(context, "tool.completed", payload)
        context.messages.append(
            ModelMessage(role="tool", content=str(result.content), tool_call_id=call.call_id)
        )
        context.context_bytes += len(str(result.content).encode())

    def _drive(self, context: RunContext) -> Iterator[EventEnvelope]:
        while context.machine.state not in {RunState.AWAITING_APPROVAL, RunState.FAILED}:
            if context.model_turns >= self.limits.max_model_turns:
                yield from self._fail(context, "max_model_turns")
                return
            if context.context_bytes >= self.limits.max_context_bytes:
                yield from self._fail(context, "max_context_bytes")
                return
            context.model_turns += 1
            yield self._event(context, "model.requested", {"turn": context.model_turns})
            try:
                turn = self.adapter.complete(self._model_request(context))
            except Exception:
                yield from self._fail(context, "model_error")
                return
            yield self._event(
                context,
                "model.completed",
                {"finish_reason": turn.finish_reason, "tool_call_count": len(turn.tool_calls)},
            )
            context.messages.append(
                ModelMessage(
                    role="assistant",
                    content=turn.assistant_text or "",
                    tool_calls=turn.tool_calls,
                )
            )
            if not turn.tool_calls:
                text = (turn.assistant_text or "").strip()
                if not text:
                    yield from self._fail(context, "empty_model_response")
                    return
                context.machine.transition(RunState.COMPLETED)
                yield self._event(context, "assistant.message", {"content": text})
                yield self._stable_event(
                    context,
                    "run.completed",
                    {"state": RunState.COMPLETED.value, "outcome": "responded"},
                    RecoveryStage.TERMINAL,
                )
                return
            context.machine.transition(RunState.GENERATING)
            for call in turn.tool_calls:
                context.tool_calls += 1
                if context.tool_calls > self.limits.max_tool_calls:
                    yield from self._fail(context, "max_tool_calls")
                    return
                yield from self._execute_tool(context, call)
                if context.machine.state in {RunState.AWAITING_APPROVAL, RunState.FAILED}:
                    return
            context.machine.transition(RunState.DISCOVERING)

    def _conversation_model_message(self, message: ConversationMessage) -> ModelMessage:
        if message.role == "summary":
            return ModelMessage(role="assistant", content=f"[会话摘要]\n{message.content}")
        return ModelMessage(role=message.role, content=message.content)

    def _start_messages(self, command: StartRun) -> list[ModelMessage]:
        system = COMPACTION_PROMPT if command.mode == "compact" else SYSTEM_PROMPT
        messages = [ModelMessage(role="system", content=system)]
        messages.extend(
            self._conversation_model_message(message) for message in command.conversation
        )
        messages.append(ModelMessage(role="user", content=command.goal))
        return messages

    def _compact(self, context: RunContext) -> Iterator[EventEnvelope]:
        yield self._event(context, "model.requested", {"turn": 1})
        try:
            turn = self.adapter.complete(
                ModelRequest(
                    messages=tuple(context.messages),
                    tools=(),
                    max_output_tokens=4_096,
                )
            )
        except Exception:
            yield from self._fail(context, "model_error")
            return
        yield self._event(
            context,
            "model.completed",
            {"finish_reason": turn.finish_reason, "tool_call_count": len(turn.tool_calls)},
        )
        if turn.tool_calls:
            yield from self._fail(context, "invalid_compaction_response")
            return
        text = (turn.assistant_text or "").strip()
        if not text:
            yield from self._fail(context, "empty_model_response")
            return
        context.machine.transition(RunState.COMPLETED)
        yield self._event(context, "conversation.compacted", {"summary": text})
        yield self._event(
            context,
            "run.completed",
            {"state": RunState.COMPLETED.value, "outcome": "compacted"},
        )

    def handle(self, command: CoreCommand) -> Iterator[EventEnvelope]:
        try:
            yield from self._dispatch(command)
        except SnapshotPersistError as exc:
            yield exc.failed_event

    def _dispatch(self, command: CoreCommand) -> Iterator[EventEnvelope]:
        if isinstance(command, CancelRun):
            context = self.runs.get(command.run_id)
            if context is not None:
                pending = context.approval_gate.pending_approval
                if pending is not None and pending.kind == ApprovalKind.RECOVERY.value:
                    self.runs.pop(command.run_id, None)
                    return
                with suppress(Exception):
                    context.machine.transition(RunState.CANCELLED)
                yield self._stable_event(
                    context,
                    "run.cancelled",
                    {"reason": "cancelled_by_user"},
                    RecoveryStage.TERMINAL,
                )
            return
        if isinstance(command, ResolveApproval):
            yield from self._resolve_approval(command)
            return
        if isinstance(command, RollbackRun):
            yield from self._rollback(command)
            return
        if isinstance(command, InspectRecovery):
            yield from self._inspect_recovery(command)
            return
        if isinstance(command, InspectState):
            yield from self._inspect_state(command)
            return
        if isinstance(command, PlanStateMigration):
            yield from self._plan_state_migration(command)
            return
        if isinstance(command, ApplyStateMigration):
            yield from self._apply_state_migration(command)
            return
        if isinstance(command, ResumeRun):
            yield from self._resume(command)
            return
        if isinstance(command, AbandonRun):
            yield from self._abandon(command)
            return
        if not isinstance(command, StartRun):
            return
        run_id = f"run_{uuid4().hex}"
        kind = "compaction" if command.mode == "compact" else "task"
        context = RunContext(
            run_id=run_id,
            command=command,
            machine=RunStateMachine(),
            journal=EventJournal(self.state_dir, run_id, Redactor([])),
            messages=self._start_messages(command),
            approval_gate=ApprovalGate(run_id),
        )
        self.runs[run_id] = context
        context.machine.transition(RunState.DISCOVERING)
        yield self._stable_event(
            context,
            "run.started",
            {
                "run_id": run_id,
                "goal": command.goal,
                "workspace_root": str(command.workspace_root),
                "model_profile": command.model_profile,
                "kind": kind,
            },
            RecoveryStage.STARTED,
        )
        if command.mode == "compact":
            yield from self._compact(context)
            return
        yield from self._drive(context)

    def _report_payload(self, report: RecoveryReport) -> dict[str, Any]:
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

    def _ephemeral_event(
        self, run_id: str, event_type: str, payload: dict[str, Any], sequence: int = 1
    ) -> EventEnvelope:
        return EventEnvelope(
            event_id=str(uuid4()),
            run_id=run_id,
            sequence=sequence,
            timestamp=datetime.now(UTC),
            type=event_type,
            payload=payload,
        )

    def _inspect_recovery(self, command: InspectRecovery) -> Iterator[EventEnvelope]:
        reports = self.coordinator.scan(command.run_id)
        for sequence, report in enumerate(reports, start=1):
            yield self._ephemeral_event(
                report.run_id, "recovery.detected", self._report_payload(report), sequence
            )

    def _inspect_state(self, command: InspectState) -> Iterator[EventEnvelope]:
        store = RunStore(self.state_dir)
        run_ids = (command.run_id,) if command.run_id else store.iter_run_ids()
        sequence = 1
        for run_id in run_ids:
            if run_id is None:
                continue
            status = store.format_status(run_id)
            yield self._ephemeral_event(
                run_id,
                "state.inspected",
                {"run_id": run_id, "format_status": status.value},
                sequence,
            )
            sequence += 1

    def _plan_state_migration(self, command: PlanStateMigration) -> Iterator[EventEnvelope]:
        service = StateMigrationService(self.state_dir)
        try:
            plan = service.plan(command.run_id)
        except Exception as exc:
            yield self._ephemeral_event(
                command.run_id,
                "state.migration_failed",
                {"run_id": command.run_id, "reason_code": str(exc)},
                1,
            )
            return
        yield self._ephemeral_event(
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

    def _apply_state_migration(self, command: ApplyStateMigration) -> Iterator[EventEnvelope]:
        service = StateMigrationService(self.state_dir)
        try:
            expected = service.plan(command.run_id)
        except Exception as exc:
            yield self._ephemeral_event(
                command.run_id,
                "state.migration_failed",
                {"run_id": command.run_id, "reason_code": str(exc)},
                1,
            )
            return
        if expected.migration_hash != command.migration_hash:
            yield self._ephemeral_event(
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
        yield self._ephemeral_event(
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

    def _reject_resume(self, report: RecoveryReport) -> Iterator[EventEnvelope]:
        sequence = 1
        if (
            report.classification is RecoveryClassification.MANUAL_REQUIRED
            and self.snapshot_store.exists(report.run_id)
        ):
            try:
                snapshot = self.snapshot_store.load(report.run_id)
            except (OSError, ValueError, RecoverySnapshotError):
                snapshot = None
            if snapshot is not None and snapshot.pending_approval is not None:
                yield self._ephemeral_event(
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
        yield self._ephemeral_event(
            report.run_id, event_type, self._report_payload(report), sequence
        )

    def _resume(self, command: ResumeRun) -> Iterator[EventEnvelope]:
        report = self.coordinator.prepare_resume(command.run_id)
        resumable = {
            RecoveryClassification.RESUMABLE_APPROVAL,
            RecoveryClassification.RESUMABLE_VERIFICATION,
            RecoveryClassification.RECOVERABLE_PARTIAL_APPLY,
        }
        if report.classification not in resumable:
            yield from self._reject_resume(report)
            return
        existing = self.runs.get(command.run_id)
        if existing is not None:
            yield self._ephemeral_event(
                report.run_id, "recovery.detected", self._report_payload(report)
            )
            if existing.approval_gate.pending_approval is not None:
                yield self._ephemeral_event(
                    existing.run_id,
                    "approval.required",
                    self._approval_payload(existing.approval_gate.pending_approval, existing),
                    2,
                )
            return
        try:
            context = RunResumer(self.coordinator).load_context(command.run_id)
        except (ResumeRejected, RecoveryHydrationError, RecoverySnapshotError, OSError, ValueError):
            yield from self._reject_resume(report)
            return
        self.runs[context.run_id] = context
        if report.classification is RecoveryClassification.RECOVERABLE_PARTIAL_APPLY:
            yield from self._propose_partial_restore(context, report)
            return
        stage = report.stage
        yield self._stable_event(
            context,
            "recovery.resume_started",
            {
                "run_id": context.run_id,
                "classification": report.classification.value,
            },
            stage,
        )
        if context.approval_gate.pending_approval is not None:
            yield self._stable_event(
                context,
                "approval.required",
                self._approval_payload(context.approval_gate.pending_approval, context),
                stage,
            )
            yield self._stable_event(
                context,
                "recovery.resumed",
                {"run_id": context.run_id},
                stage,
            )
            return
        yield self._stable_event(
            context,
            "recovery.resumed",
            {"run_id": context.run_id},
            stage,
        )
        yield from self._verify(context)

    def _propose_partial_restore(
        self, context: RunContext, report: RecoveryReport
    ) -> Iterator[EventEnvelope]:
        snapshot = self.snapshot_store.load(context.run_id)
        try:
            plan = RecoveryPlanner().plan(report, snapshot)
        except RecoveryPlanError:
            yield from self._reject_resume(report)
            return
        current = context.pending_recovery_plan
        pending = context.approval_gate.pending_approval
        if current is None or current.recovery_hash != plan.recovery_hash:
            if pending is not None:
                yield self._stable_event(
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
                workspace_identity=self._policy_binding(context.command.workspace_root)[0],
                policy_hash=self.policy_engine.policy_hash,
            )
        else:
            context.pending_recovery_plan = current
        stage = report.stage
        yield self._stable_event(
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
        yield self._stable_event(
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
        yield self._stable_event(
            context,
            "approval.required",
            self._approval_payload(pending, context),
            stage,
        )

    def _apply_recovery_plan(
        self, context: RunContext, request: ApprovalRequest
    ) -> Iterator[EventEnvelope]:
        plan = context.pending_recovery_plan
        manifest = context.checkpoint_manifest
        if plan is None or manifest is None:
            yield from self._fail(context, "missing_recovery_plan")
            return
        report = self.coordinator.prepare_resume(context.run_id)
        try:
            snapshot = self.snapshot_store.load(context.run_id)
            recomputed = RecoveryPlanner().plan(report, snapshot)
        except (RecoveryPlanError, RecoverySnapshotError, OSError, ValueError):
            yield self._stable_event(
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
            yield self._stable_event(
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
        paths = WorkspacePaths(context.command.workspace_root)
        result = ChangeApplier(
            paths,
            CheckpointStore(self.state_dir, paths),
            writer=self.file_writer,
        ).restore_partial(plan, manifest)
        if result.status is not RollbackStatus.ROLLED_BACK:
            with suppress(Exception):
                context.machine.transition(RunState.RECOVERY_REQUIRED)
            yield self._stable_event(
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
        yield self._stable_event(
            context,
            "recovery.restored",
            {"run_id": context.run_id, "paths": list(result.paths)},
            RecoveryStage.TERMINAL,
        )
        yield self._stable_event(
            context,
            "run.completed",
            {"state": "completed", "outcome": "restored"},
            RecoveryStage.TERMINAL,
        )

    def _context_from_snapshot(self, run_id: str) -> RunContext:
        snapshot = self.snapshot_store.load(run_id)
        journal = EventJournal(self.state_dir, run_id, Redactor([]))
        try:
            return RecoveryHydrator().hydrate(snapshot, journal)
        except RecoveryHydrationError:
            return RunContext(
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

    def _abandon(self, command: AbandonRun) -> Iterator[EventEnvelope]:
        report = self.coordinator.prepare_resume(command.run_id)
        if "abandon" not in report.allowed_actions:
            yield self._ephemeral_event(
                report.run_id,
                "recovery.manual_required",
                self._report_payload(report),
            )
            return
        context = self.runs.get(command.run_id)
        if context is None:
            try:
                context = self._context_from_snapshot(command.run_id)
            except (RecoverySnapshotError, OSError, ValueError):
                yield from self._reject_resume(report)
                return
            self.runs[context.run_id] = context
        with suppress(Exception):
            context.machine.transition(RunState.CANCELLED)
        yield self._stable_event(
            context,
            "recovery.abandoned",
            {
                "run_id": context.run_id,
                "classification": report.classification.value,
            },
            RecoveryStage.TERMINAL,
        )
