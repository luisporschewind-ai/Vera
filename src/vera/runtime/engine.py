"""Bounded discovery loop that stops before any filesystem mutation."""

from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel

from vera.config import Limits
from vera.contracts.commands import CancelRun, CoreCommand, ResolveApproval, RollbackRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelAdapter, ModelMessage, ModelRequest, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.prompts import SYSTEM_PROMPT
from vera.runtime.state import RunState, RunStateMachine
from vera.tools.command_policy import CommandDecisionKind, CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.verification.runner import VerificationRunner
from vera.workspace.apply import ApplyStatus, ChangeApplier, RollbackStatus
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


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
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.state_dir = state_dir
        self.limits = limits or Limits()
        self.runs: dict[str, RunContext] = {}

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope:
        return context.journal.append(event_type, payload)

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
        yield self._event(context, "run.failed", {"reason": reason})

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
                "files": [item.path for item in change_set.files],
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
        yield self._event(
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
        )

    def _verify(self, context: RunContext) -> Iterator[EventEnvelope]:
        built = context.built_change_set
        if built is None:
            yield from self._fail(context, "missing_changeset")
            return
        runner = VerificationRunner(context.command.workspace_root)
        policy = CommandPolicy()
        verification_failed = False
        for index, command in enumerate(built.change_set.verification):
            decision = policy.classify(command)
            if decision.kind is CommandDecisionKind.FORBIDDEN:
                verification_failed = True
                yield self._event(
                    context,
                    "verification.completed",
                    {"index": index, "status": "rejected", "reason": decision.reason},
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
                yield self._event(
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
                )
                return
            yield self._event(
                context,
                "verification.started",
                {"index": index, "argv": list(command.argv), "cwd": command.cwd},
            )
            result = runner.run(command)
            verification_failed = verification_failed or result.status != "passed"
            yield self._event(
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
            )
        terminal = RunState.VERIFICATION_FAILED if verification_failed else RunState.COMPLETED
        context.machine.transition(terminal)
        yield self._event(context, "run.completed", {"state": context.machine.state.value})

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
        if decision == "reject":
            context.machine.transition(RunState.CANCELLED)
            yield self._event(context, "run.cancelled", {"reason": "approval_rejected"})
            return
        if request.kind == ApprovalKind.COMMAND.value:
            if context.pending_command is not None:
                result = VerificationRunner(context.command.workspace_root).run(
                    context.pending_command
                )
                yield self._event(
                    context,
                    "verification.completed",
                    {"status": result.status, "exit_code": result.exit_code},
                )
                context.pending_command = None
            yield from self._verify(context)
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
        yield self._event(context, "checkpoint.created", {"checkpoint_id": manifest.checkpoint_id})
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
        yield self._event(context, "changeset.applied", {"status": apply_result.status.value})
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
        if context is None:
            return
        paths = WorkspacePaths(context.command.workspace_root)
        manifest = CheckpointStore(self.state_dir, paths).load_for_run(context.run_id)
        result = ChangeApplier(paths, CheckpointStore(self.state_dir, paths)).rollback(manifest)
        if result.status is RollbackStatus.ROLLED_BACK:
            yield self._event(context, "rollback.completed", {"paths": list(result.paths)})
        else:
            yield self._event(
                context,
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
            if not turn.tool_calls:
                yield from self._fail(context, "no_changes_proposed")
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

    def handle(self, command: CoreCommand) -> Iterator[EventEnvelope]:
        if isinstance(command, CancelRun):
            context = self.runs.get(command.run_id)
            if context is not None:
                with suppress(Exception):
                    context.machine.transition(RunState.CANCELLED)
                yield self._event(context, "run.cancelled", {"reason": "cancelled_by_user"})
            return
        if isinstance(command, ResolveApproval):
            yield from self._resolve_approval(command)
            return
        if isinstance(command, RollbackRun):
            yield from self._rollback(command)
            return
        if not isinstance(command, StartRun):
            return
        run_id = f"run_{uuid4().hex}"
        context = RunContext(
            run_id=run_id,
            command=command,
            machine=RunStateMachine(),
            journal=EventJournal(self.state_dir, run_id, Redactor([])),
            messages=[
                ModelMessage(role="system", content=SYSTEM_PROMPT),
                ModelMessage(role="user", content=command.goal),
            ],
            approval_gate=ApprovalGate(run_id),
        )
        self.runs[run_id] = context
        context.machine.transition(RunState.DISCOVERING)
        yield self._event(context, "run.started", {"run_id": run_id, "goal": command.goal})
        yield from self._drive(context)
