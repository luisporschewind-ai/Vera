"""Bounded discovery loop that stops before any filesystem mutation."""

from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel

from vera.config import Limits
from vera.contracts.commands import CoreCommand, StartRun
from vera.contracts.events import EventEnvelope
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelAdapter, ModelMessage, ModelRequest, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.prompts import SYSTEM_PROMPT
from vera.runtime.state import RunState, RunStateMachine
from vera.tools.registry import ToolRegistry
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
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
                "kind": request.kind,
                "target_id": request.target_id,
                "target_hash": request.target_hash,
                "description": request.description,
                "risk": request.risk,
            },
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
