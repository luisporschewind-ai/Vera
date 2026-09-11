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
from vera.contracts.commands import (
    CancelRun,
    CoreCommand,
    InspectRecovery,
    ResolveApproval,
    RollbackRun,
    StartRun,
)
from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelAdapter, ModelMessage, ModelRequest, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.models import PersistedChangeSet, RecoverySnapshot
from vera.recovery.probe import workspace_identity
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.prompts import COMPACTION_PROMPT, SYSTEM_PROMPT
from vera.runtime.state import RunState, RunStateMachine
from vera.tools.command_policy import CommandDecisionKind, CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.verification.runner import VerificationRunner
from vera.workspace.apply import ApplyStatus, ChangeApplier, RollbackStatus
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
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.state_dir = state_dir
        self.limits = limits or Limits()
        self.command_policy = command_policy or CommandPolicy()
        self.runs: dict[str, RunContext] = {}
        self.snapshot_store = snapshot_store or RecoverySnapshotStore(state_dir)
        self.installation_id = installation_id or "local"
        self.coordinator = recovery_coordinator or RecoveryCoordinator(
            state_dir,
            self.installation_id,
            snapshot_store=self.snapshot_store,
        )

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
        )
        yield self._stable_event(
            context,
            "approval.required",
            {
                "approval_id": request.approval_id,
                "run_id": context.run_id,
                "kind": request.kind,
                "target_id": request.target_id,
                "target_hash": request.target_hash,
                "description": request.description,
                "risk": request.risk,
            },
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
                )
                yield self._stable_event(
                    context,
                    "approval.required",
                    {
                        "run_id": context.run_id,
                        "approval_id": request.approval_id,
                        "kind": request.kind,
                        "target_id": request.target_id,
                        "target_hash": request.target_hash,
                        "argv": list(command.argv),
                        "cwd": command.cwd,
                        "risk": request.risk,
                    },
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
        applier = ChangeApplier(paths, store)
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

    def _inspect_recovery(self, command: InspectRecovery) -> Iterator[EventEnvelope]:
        reports = self.coordinator.scan(command.run_id)
        for sequence, report in enumerate(reports, start=1):
            yield EventEnvelope(
                event_id=str(uuid4()),
                run_id=report.run_id,
                sequence=sequence,
                timestamp=datetime.now(UTC),
                type="recovery.detected",
                payload={
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
                },
            )
