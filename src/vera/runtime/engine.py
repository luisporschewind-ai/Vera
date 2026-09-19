"""Bounded discovery loop that stops before any filesystem mutation."""

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import sleep as default_sleep
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, field_validator

from vera import __version__
from vera.config import Limits
from vera.content.detector import (
    BaselinePromptInjectionDetector,
    ContentDetector,
    DetectionDisposition,
    SafeContentDetector,
)
from vera.content.envelope import (
    EMPTY_SECURITY_CONTEXT_HASH,
    build_content_envelope,
    render_content_for_model,
    render_project_guidance_for_model,
)
from vera.content.trust import source_kind_for_path
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
from vera.contracts.streaming import RuntimeOutput, StreamFrame, StreamFrameType
from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.models.base import ModelAdapter, ModelMessage, ModelRequest, ModelToolCall, ModelTurn
from vera.models.errors import ModelErrorCode, ModelProviderError, safe_error_payload
from vera.models.retry import RetryPolicy
from vera.models.streaming import ModelStreamCompleted, ModelTextDelta
from vera.persistence.journal import EventJournal
from vera.persistence.migration import StateMigrationService
from vera.persistence.operation_receipt import (
    OperationReceipt,
    OperationReceiptStore,
    receipt_key,
)
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.persistence.run_store import RunStore
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.project_instructions import ProjectInstructionService
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.hydrator import RecoveryHydrationError, RecoveryHydrator
from vera.recovery.models import PersistedChangeSet, PersistedToolAction, RecoverySnapshot
from vera.recovery.planner import RecoveryPlanError, RecoveryPlanner
from vera.recovery.probe import workspace_identity
from vera.recovery.resume import ResumeRejected, RunResumer
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate, ApprovalKind, ApprovalMismatch
from vera.runtime.context import RunContext, compact_run_messages, tool_result_message
from vera.runtime.prompts import COMPACTION_PROMPT, SYSTEM_PROMPT
from vera.runtime.security import (
    MAX_SECURITY_FINDINGS,
    collected_risk_labels,
    current_security_hash,
    merge_finding,
    security_payload,
    worst_disposition,
)
from vera.runtime.state import RunState, RunStateMachine
from vera.tools.command_policy import CommandDecisionKind, CommandPolicy
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.executor import PreparedToolAction, ToolExecutor, ToolPreparationError
from vera.tools.registry import ToolRegistry
from vera.verification.artifacts import (
    VerificationArtifactError,
    VerificationArtifactPlanner,
    artifact_root,
)
from vera.verification.runner import VerificationRunner
from vera.workspace.apply import ApplyStatus, ChangeApplier, FileWriter, RollbackStatus
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder, sha256_bytes
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths

_TOOL_LIMIT_WRAP_UP = (
    "工具调用次数已达本次任务上限。请只根据已经收集到的证据给出结论，不要再调用任何工具。"
)
_TOOL_LIMIT_SKIPPED = (
    '{"content_hash":"","notice":"skipped: tool call budget exhausted","vera_content":1}'
)
_EMPTY_AFTER_TOOLS_NUDGE = (
    "上一次回复没有文本也没有工具调用。请根据已经收集到的证据给出最终中文回答，"
    "或调用 propose_changeset；不要返回空响应。"
)
_CLAIMED_CHANGESET_NUDGE = (
    "你还没有调用 propose_changeset。只有该工具才会出现审批卡和 Diff；"
    "不要声称已经形成 Change Set 或正在等待审批。"
    "若要改文件，现在就调用 propose_changeset；否则只说明结论，不要假装变更已提交。"
)
_CLAIMED_CHANGESET_MARKERS = (
    "已形成 change set",
    "已形成 changeset",
    "等待你审批",
    "等待审批",
)


def claims_unissued_changeset(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in _CLAIMED_CHANGESET_MARKERS)


def tool_call_target(call: ModelToolCall) -> str:
    arguments = call.arguments if isinstance(call.arguments, dict) else {}
    if call.name == "propose_changeset":
        summary = arguments.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        changes = arguments.get("changes")
        if isinstance(changes, list) and changes:
            first = changes[0]
            if isinstance(first, dict) and first.get("path"):
                extra = f" 等{len(changes)}个文件" if len(changes) > 1 else ""
                return f"{first['path']}{extra}"
        return ""
    path = arguments.get("path")
    query = arguments.get("query")
    if call.name == "search_text" and isinstance(query, str) and query:
        if isinstance(path, str) and path and path != ".":
            return f"{query} @ {path}"
        return query
    if isinstance(path, str) and path:
        return path
    return ""


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

    @field_validator("verification", mode="before")
    @classmethod
    def ignore_model_artifact_plan(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        cleaned: list[object] = []
        for item in value:
            if isinstance(item, dict):
                payload = dict(item)
                payload.pop("artifact_plan", None)
                cleaned.append(payload)
            elif isinstance(item, VerificationCommand):
                cleaned.append(item.model_copy(update={"artifact_plan": None}))
            else:
                cleaned.append(item)
        return cleaned


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
        artifact_prefix: Path | None = None,
        recovery_coordinator: RecoveryCoordinator | None = None,
        file_writer: FileWriter | None = None,
        policy_engine: PolicyEngine | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = default_sleep,
        content_detector: ContentDetector | None = None,
        project_instructions: ProjectInstructionService | None = None,
        workspace_permissions: WorkspacePermissionSnapshot | None = None,
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.state_dir = state_dir
        self.limits = limits or Limits()
        self.installation_id = installation_id or "local"
        self.artifact_prefix = artifact_prefix
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=self.limits.max_model_attempts)
        self.sleep = sleep
        self.content_detector = SafeContentDetector(
            content_detector or BaselinePromptInjectionDetector()
        )
        self.project_instructions = project_instructions or ProjectInstructionService()
        self._uses_default_policy = policy_engine is None and command_policy is None
        if policy_engine is not None:
            self.policy_engine = policy_engine
        elif command_policy is not None:
            self.policy_engine = command_policy.engine
        else:
            self.policy_engine = PolicyEngine(
                EffectivePolicySnapshotV2(workspace_identity="default")
            )
        self.command_policy = command_policy or CommandPolicy(
            self.policy_engine.snapshot.user_allowed_command_prefixes,
            policy_engine=self.policy_engine,
            workspace_identity=self.policy_engine.snapshot.workspace_identity,
        )
        self.workspace_permissions = workspace_permissions
        self.runs: dict[str, RunContext] = {}
        self.snapshot_store = snapshot_store or RecoverySnapshotStore(state_dir)
        self.receipts = OperationReceiptStore(state_dir)
        self.file_writer = file_writer
        self.coordinator = recovery_coordinator or RecoveryCoordinator(
            state_dir,
            self.installation_id,
            snapshot_store=self.snapshot_store,
        )

    def _policy_binding(self, root: Path) -> tuple[str, str]:
        identity = workspace_identity(root, self.installation_id)
        return identity, self.policy_engine.policy_hash

    def _bind_default_policy_to_workspace(self, root: Path) -> None:
        snapshot = self.policy_engine.snapshot
        if (
            not self._uses_default_policy
            or not isinstance(snapshot, EffectivePolicySnapshotV2)
            or (snapshot.workspace_identity != "default")
        ):
            return
        bound = snapshot.model_copy(
            update={"workspace_identity": workspace_identity(root, self.installation_id)}
        )
        self.policy_engine = PolicyEngine(bound)
        self.command_policy = CommandPolicy(
            bound.user_allowed_command_prefixes,
            policy_engine=self.policy_engine,
            workspace_identity=bound.workspace_identity,
        )

    def _tool_executor(self, context: RunContext) -> ToolExecutor:
        """Bind ordinary tools to the current v2 Policy before they can execute.

        A v1 engine can still exist while resuming historical Phase-6 state.  It is
        projected to its equivalent v2 fields solely for ordinary read-tool
        compatibility; new bootstraps always inject a native v2 engine.
        """

        snapshot = self.policy_engine.snapshot
        engine = self.policy_engine
        current_identity = workspace_identity(context.command.workspace_root, self.installation_id)
        if not isinstance(snapshot, EffectivePolicySnapshotV2):
            snapshot = EffectivePolicySnapshotV2(
                workspace_identity=current_identity,
                protected_path_globs=snapshot.protected_path_globs,
                user_allowed_command_prefixes=snapshot.user_allowed_command_prefixes,
                project_denied_path_globs=snapshot.project_denied_path_globs,
                project_denied_tools=snapshot.project_denied_tools,
            )
            engine = PolicyEngine(snapshot)
        permissions = self.workspace_permissions
        if permissions is None:
            permissions = WorkspacePermissionSnapshot(
                workspace_identity=current_identity,
                policy_major_version=snapshot.builtin_policy_version,
                protected_roots_hash=snapshot.protected_roots_hash,
                trusted=False,
            )
        return ToolExecutor(
            self.registry,
            engine,
            permissions,
            goal_authorized=bool(context.command.goal.strip()),
        )

    def _security_approval_kwargs(self, context: RunContext) -> dict[str, Any]:
        return {
            "security_context_hash": context.security_context_hash or EMPTY_SECURITY_CONTEXT_HASH,
            "risk_labels": collected_risk_labels(context.security_findings),
            "risk_sources": tuple(item.envelope for item in context.security_findings),
        }

    def _prepare_content(
        self,
        context: RunContext,
        text: str,
        *,
        source_kind: str | None,
        origin: str,
        truncated: bool = False,
    ) -> tuple[Any, str, list[EventEnvelope]]:
        envelope = build_content_envelope(
            text,
            source_kind=source_kind,
            origin=origin,
            truncated=truncated,
        )
        detection = self.content_detector.assess(envelope, text)
        envelope = envelope.model_copy(update={"risk_labels": detection.risk_labels})
        events: list[EventEnvelope] = []
        if detection.disposition is not DetectionDisposition.CLEAR:
            events.extend(self._record_finding(context, envelope, detection))
        return envelope, render_content_for_model(envelope, text), events

    def _record_finding(
        self, context: RunContext, envelope: Any, detection: Any
    ) -> list[EventEnvelope]:
        if context.findings_truncated:
            return []
        merged, added = merge_finding(context.security_findings, envelope, detection)
        if not added:
            return []
        if len(context.security_findings) >= MAX_SECURITY_FINDINGS:
            context.findings_truncated = True
            return [
                self._event(
                    context,
                    "security.findings_truncated",
                    {"limit": MAX_SECURITY_FINDINGS, "dropped": True},
                )
            ]
        context.security_findings = merged
        context.security_context_hash = current_security_hash(merged)
        return [
            self._event(context, "security.content_flagged", security_payload(envelope, detection))
        ]

    def _seed_context(self, context: RunContext) -> Iterator[EventEnvelope]:
        command = context.command
        system = COMPACTION_PROMPT if command.mode == "compact" else SYSTEM_PROMPT
        context.messages.append(ModelMessage(role="system", content=system))
        if command.mode != "compact":
            yield from self._seed_project_instructions(context)
        for message in command.conversation:
            yield from self._append_conversation_message(context, message)
        envelope, rendered, events = self._prepare_content(
            context,
            command.goal,
            source_kind="user_goal",
            origin="start_run.goal",
        )
        del envelope
        context.messages.append(ModelMessage(role="user", content=rendered))
        yield from events
        context.context_bytes = sum(len(item.content.encode("utf-8")) for item in context.messages)

    def _seed_project_instructions(self, context: RunContext) -> Iterator[EventEnvelope]:
        loaded = self.project_instructions.load(context.command.workspace_root)
        context.project_instructions = loaded
        yield self._event(
            context,
            "project.instructions.loaded",
            {
                "guidance_hash": loaded.guidance_hash,
                "sources": [
                    {
                        "name": item.name,
                        "priority": item.priority,
                        "content_hash": item.content_hash,
                        "byte_count": item.byte_count,
                    }
                    for item in loaded.sources
                ],
            },
        )
        if loaded.issues:
            yield self._event(
                context,
                "project.instructions.skipped",
                {
                    "issues": [
                        {"name": item.name, "reason_code": item.reason_code}
                        for item in loaded.issues
                    ],
                },
            )
        rendered_items: list[tuple[Any, str, int]] = []
        for source in loaded.sources:
            envelope, _rendered, events = self._prepare_content(
                context,
                source.content,
                source_kind="project_guidance",
                origin=source.name,
            )
            yield from events
            rendered_items.append((envelope, source.content, source.priority))
        if rendered_items:
            context.messages.append(
                ModelMessage(
                    role="user",
                    content=render_project_guidance_for_model(rendered_items),
                )
            )

    def _append_conversation_message(
        self, context: RunContext, message: ConversationMessage
    ) -> Iterator[EventEnvelope]:
        role: Literal["user", "assistant"]
        if message.role == "summary":
            source_kind, origin, role = "conversation_summary", "conversation.summary", "assistant"
        elif message.role == "assistant":
            source_kind, origin, role = "model_output", "conversation.assistant", "assistant"
        else:
            source_kind, origin, role = "user_goal", "conversation.user", "user"
        _envelope, rendered, events = self._prepare_content(
            context,
            message.content,
            source_kind=source_kind,
            origin=origin,
        )
        context.messages.append(ModelMessage(role=role, content=rendered))
        yield from events

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
            "fact_hash": request.fact_hash,
            "security_context_hash": request.security_context_hash,
            "risk_labels": list(request.risk_labels),
            "risk_sources": [item.model_dump(mode="json") for item in request.risk_sources],
        }
        if (
            context is not None
            and request.kind == ApprovalKind.COMMAND.value
            and context.pending_command is not None
        ):
            payload["argv"] = list(context.pending_command.argv)
            payload["cwd"] = context.pending_command.cwd
            plan = context.pending_command.artifact_plan
            if plan is not None:
                payload["artifact_profile"] = plan.profile
                payload["artifact_root"] = plan.root
        if (
            context is not None
            and request.kind == ApprovalKind.TOOL.value
            and context.pending_tool_action is not None
        ):
            pending = context.pending_tool_action
            payload["tool_name"] = pending.action.tool_name
            payload["action_id"] = pending.action.action_id
            payload["input_hash"] = pending.action.input_hash
            payload["target_facts_hash"] = pending.target_facts_hash
        return payload

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope:
        return context.journal.append(event_type, payload)

    def _replay_receipt(self, receipt: OperationReceipt) -> Iterator[EventEnvelope]:
        path = self.state_dir / "runs" / receipt.run_id / "events.jsonl"
        if not path.is_file():
            return
        wanted = {
            ref.removeprefix("event:") for ref in receipt.effect_refs if ref.startswith("event:")
        }
        for event in EventJournal.load_events(path, receipt.run_id):
            if event.event_id in wanted:
                yield event

    def _file_effect_refs(self, run_id: str) -> tuple[str, ...]:
        context = self.runs.get(run_id)
        if context is None or context.built_change_set is None:
            return ()
        refs: list[str] = []
        root = context.command.workspace_root
        for item in context.built_change_set.change_set.files:
            target = root / item.path
            digest = sha256_bytes(target.read_bytes()) if target.exists() else "0" * 64
            refs.append(f"file:{item.path}:{digest}")
        return tuple(refs)

    def _commit_receipt(
        self,
        *,
        operation: Literal["resume", "resolve_approval", "cancel", "rollback"],
        run_id: str,
        payload: dict[str, Any],
        events: Sequence[EventEnvelope],
        extra_refs: tuple[str, ...] = (),
    ) -> None:
        if not events:
            return
        operation_id, input_hash = receipt_key(operation, payload)
        self.receipts.save(
            OperationReceipt(
                operation_id=operation_id,
                operation=operation,
                run_id=run_id,
                input_hash=input_hash,
                terminal_result=events[-1].type,
                effect_refs=tuple(f"event:{event.event_id}" for event in events) + extra_refs,
                created_at=datetime.now(UTC),
            )
        )

    def _with_receipt(
        self,
        operation: Literal["resume", "resolve_approval", "cancel", "rollback"],
        run_id: str,
        payload: dict[str, Any],
        events: Iterator[EventEnvelope],
        *,
        extra_refs: Callable[[], tuple[str, ...]] | None = None,
        hydrate: bool = False,
    ) -> Iterator[EventEnvelope]:
        operation_id, _input_hash = receipt_key(operation, payload)
        existing = self.receipts.load(run_id, operation_id)
        if existing is not None:
            if hydrate and run_id not in self.runs:
                with suppress(Exception):
                    self.runs[run_id] = RunResumer(self.coordinator).load_context(run_id)
            yield from self._replay_receipt(existing)
            return
        collected: list[EventEnvelope] = []
        for event in events:
            collected.append(event)
            yield event
        refs = extra_refs() if extra_refs is not None else ()
        self._commit_receipt(
            operation=operation,
            run_id=run_id,
            payload=payload,
            events=collected,
            extra_refs=refs,
        )

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
            pending_tool_action=context.pending_tool_action,
            checkpoint_id=checkpoint_id,
            pending_approval=context.approval_gate.pending_approval,
            verification_index=context.verification_index,
            verification_failed=context.verification_failed,
            verification_in_flight=verification_in_flight,
            workspace_write_started=context.workspace_write_started,
            recovery_plan=context.pending_recovery_plan,
            security_findings=context.security_findings,
            security_context_hash=context.security_context_hash,
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

    def _definitions(self) -> tuple[ToolDefinitionV2, ...]:
        return self.registry.definitions()

    def _model_request(self, context: RunContext) -> ModelRequest:
        return ModelRequest(
            messages=tuple(context.messages),
            tools=self._definitions(),
            max_output_tokens=4_096,
        )

    def _fail(self, context: RunContext, reason: str) -> Iterator[EventEnvelope]:
        with suppress(Exception):
            context.machine.transition(RunState.FAILED)
        yield self._stable_event(context, "run.failed", {"reason": reason}, RecoveryStage.TERMINAL)

    def _planner(self) -> VerificationArtifactPlanner:
        return VerificationArtifactPlanner(prefix=self.artifact_prefix)

    def _verification_runner(self, context: RunContext) -> VerificationRunner:
        return VerificationRunner(
            context.command.workspace_root,
            artifact_prefix=self.artifact_prefix,
        )

    def _plan_verification(
        self,
        context: RunContext,
        commands: Sequence[VerificationCommand],
    ) -> tuple[VerificationCommand, ...]:
        planner = self._planner()
        planned: list[VerificationCommand] = []
        for index, command in enumerate(commands):
            planned.append(
                planner.plan(
                    command,
                    workspace_root=context.command.workspace_root,
                    installation_id=self.installation_id,
                    run_id=context.run_id,
                    index=index,
                )
            )
        return tuple(planned)

    def _expected_artifact_root(self, context: RunContext, index: int) -> Path:
        return artifact_root(
            workspace_root=context.command.workspace_root,
            installation_id=self.installation_id,
            run_id=context.run_id,
            index=index,
            prefix=self.artifact_prefix,
        )

    def _verification_binding_matches(
        self, context: RunContext, command: VerificationCommand, index: int
    ) -> bool:
        plan = command.artifact_plan
        if plan is None or plan.root is None:
            return False
        return plan.root == str(self._expected_artifact_root(context, index))

    def _verification_event_payload(
        self,
        index: int,
        command: VerificationCommand,
        result: VerificationResult | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = command.artifact_plan
        payload: dict[str, Any] = {
            "index": index,
            "argv": list(command.argv),
            "cwd": command.cwd,
            "artifact_profile": None if plan is None else plan.profile,
            "artifact_root": None if plan is None else plan.root,
        }
        if result is not None:
            payload.update(
                {
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "stdout_truncated": result.stdout_truncated,
                    "stderr_truncated": result.stderr_truncated,
                    "artifact_cleanup_status": result.artifact_cleanup_status,
                    "workspace_mutations": list(result.workspace_mutations),
                    "reason_code": result.reason_code,
                }
            )
        if extra:
            payload.update(extra)
        return payload

    def _reject_tool(
        self, context: RunContext, call: ModelToolCall, payload: dict[str, Any]
    ) -> Iterator[EventEnvelope]:
        failed = {"name": call.name, "call_id": call.call_id, "ok": False, **payload}
        target = tool_call_target(call)
        if target:
            failed["target"] = target
        yield self._event(context, "tool.completed", failed)
        rendered = json.dumps(failed, ensure_ascii=False, sort_keys=True)
        context.messages.append(
            ModelMessage(
                role="tool",
                content=tool_result_message(call, ToolResult(ok=False, content=failed), rendered),
                tool_call_id=call.call_id,
            )
        )
        context.context_bytes = sum(
            len(message.content.encode("utf-8")) for message in context.messages
        )

    def _propose(self, context: RunContext, call: ModelToolCall) -> Iterator[EventEnvelope]:
        try:
            proposal = ProposalInput.model_validate(call.arguments)
            invalid_init = context.command.mode == "project_init" and (
                len(proposal.changes) != 1
                or proposal.changes[0].path != "VERA.md"
                or proposal.changes[0].operation not in {"create", "update"}
                or proposal.verification
            )
            if invalid_init:
                yield from self._fail(context, "project_init_scope_violation")
                return
            planned = self._plan_verification(context, proposal.verification)
            built = ChangeSetBuilder(WorkspacePaths(context.command.workspace_root)).build(
                context.run_id,
                proposal.summary,
                proposal.changes,
                planned,
            )
        except VerificationArtifactError as exc:
            yield from self._reject_tool(
                context,
                call,
                {
                    "error": exc.code,
                    "reason_code": exc.code,
                    "basename": exc.basename,
                    "suggestion": exc.suggestion,
                },
            )
            return
        except Exception as exc:
            if context.command.mode == "project_init":
                yield from self._fail(context, "project_init_scope_violation")
                return
            yield from self._reject_tool(context, call, {"error": str(exc)})
            return
        change_set = built.change_set
        if context.command.mode == "project_init":
            try:
                self.project_instructions.validate_init_changeset(change_set)
            except ValueError:
                yield from self._fail(context, "project_init_scope_violation")
                return
        context.built_change_set = built
        context.machine.transition(RunState.CHANGESET_PROPOSED)
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
        if context.security_findings:
            risk = "high"
        request = context.approval_gate.require(
            ApprovalKind.CHANGESET,
            change_set.changeset_id,
            change_set.content_hash,
            change_set.summary,
            risk,
            workspace_identity=self._policy_binding(context.command.workspace_root)[0],
            policy_hash=self.policy_engine.policy_hash,
            fact_hash=built.facts_digest(),
            **self._security_approval_kwargs(context),
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
        runner = self._verification_runner(context)
        policy = self.command_policy
        while context.verification_index < len(built.change_set.verification):
            index = context.verification_index
            command = built.change_set.verification[index]
            if not self._verification_binding_matches(context, command, index):
                context.verification_failed = True
                context.verification_index += 1
                context.pending_command = None
                yield self._stable_event(
                    context,
                    "verification.completed",
                    self._verification_event_payload(
                        index,
                        command,
                        extra={
                            "status": "rejected",
                            "reason_code": "verification_not_planned",
                        },
                    ),
                    RecoveryStage.VERIFYING,
                )
                continue
            decision = policy.classify(
                command,
                risk_labels=collected_risk_labels(context.security_findings),
                detector_disposition=worst_disposition(context.security_findings),
            )
            if decision.kind is CommandDecisionKind.FORBIDDEN:
                context.verification_failed = True
                context.verification_index += 1
                yield self._stable_event(
                    context,
                    "verification.completed",
                    self._verification_event_payload(
                        index,
                        command,
                        extra={"status": "rejected", "reason": decision.reason},
                    ),
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
                    "high" if context.security_findings else "medium",
                    workspace_identity=self._policy_binding(context.command.workspace_root)[0],
                    policy_hash=self.policy_engine.policy_hash,
                    **self._security_approval_kwargs(context),
                )
                payload = self._approval_payload(request, context)
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
                self._verification_event_payload(index, command),
                RecoveryStage.VERIFYING,
            )
            result = runner.run(command)
            context.verification_failed = context.verification_failed or result.status != "passed"
            context.verification_index += 1
            yield self._stable_event(
                context,
                "verification.completed",
                self._verification_event_payload(index, command, result),
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

    def _expire_approval(
        self,
        context: RunContext | None,
        command: ResolveApproval,
        reason: str,
        approval_id: str | None = None,
    ) -> Iterator[EventEnvelope]:
        payload = {
            "approval_id": approval_id or command.approval_id,
            "run_id": command.run_id,
            "expiry_reason": reason,
        }
        if context is None:
            yield EventEnvelope(
                event_id=f"event_{uuid4().hex}",
                run_id=command.run_id,
                sequence=1,
                timestamp=datetime.now(UTC),
                type="approval.expired",
                payload=payload,
            )
            return
        yield self._stable_event(
            context,
            "approval.expired",
            payload,
            RecoveryStage.AWAITING_CHANGESET_APPROVAL,
        )

    def _resolve_approval(self, command: ResolveApproval) -> Iterator[EventEnvelope]:
        context = self.runs.get(command.run_id)
        if context is None:
            yield from self._expire_approval(None, command, "cross_run")
            return
        request = context.approval_gate.pending_approval
        if request is None:
            return
        try:
            decision = context.approval_gate.resolve(command)
        except ApprovalMismatch as exc:
            yield from self._expire_approval(
                context,
                command,
                exc.reason,
                approval_id=request.approval_id,
            )
            return
        identity, current_hash = self._policy_binding(context.command.workspace_root)
        if request.policy_hash is not None and request.policy_hash != current_hash:
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
        current_security = context.security_context_hash or EMPTY_SECURITY_CONTEXT_HASH
        request_security = request.security_context_hash or EMPTY_SECURITY_CONTEXT_HASH
        if request_security != current_security:
            yield self._stable_event(
                context,
                "approval.invalidated",
                {
                    "approval_id": request.approval_id,
                    "run_id": context.run_id,
                    "reason_code": "security_context_changed",
                },
                RecoveryStage.AWAITING_CHANGESET_APPROVAL,
            )
            return
        if decision == "approve" and request.kind == ApprovalKind.CHANGESET.value:
            if not request.fact_hash:
                yield from self._expire_approval(
                    context,
                    command,
                    "missing_fact_binding",
                    approval_id=request.approval_id,
                )
                return
            built = context.built_change_set
            expired = built is None or built.facts_digest() != request.fact_hash
            if not expired and built is not None:
                paths = WorkspacePaths(context.command.workspace_root)
                try:
                    for fact in built.path_facts.values():
                        paths.revalidate(fact)
                except WorkspaceBoundaryError:
                    expired = True
            if expired:
                yield from self._expire_approval(
                    context,
                    command,
                    "fact_changed",
                    approval_id=request.approval_id,
                )
                return
        if request.kind == ApprovalKind.COMMAND.value:
            pending = context.pending_command
            if pending is None or not self._verification_binding_matches(
                context, pending, context.verification_index
            ):
                yield from self._expire_approval(
                    context,
                    command,
                    "verification_binding_changed",
                    approval_id=request.approval_id,
                )
                return
        if request.kind == ApprovalKind.TOOL.value:
            pending_tool = context.pending_tool_action
            if (
                pending_tool is None
                or pending_tool.action.action_id != request.target_id
                or pending_tool.action.input_hash != request.target_hash
                or pending_tool.target_facts_hash != request.fact_hash
            ):
                yield from self._expire_approval(
                    context,
                    command,
                    "tool_binding_changed",
                    approval_id=request.approval_id,
                )
                return
        yield self._event(
            context,
            "approval.resolved",
            {"approval_id": request.approval_id, "decision": decision, "kind": request.kind},
        )
        if request.kind == ApprovalKind.COMMAND.value:
            if decision == "reject":
                index = context.verification_index
                pending = context.pending_command
                context.verification_failed = True
                context.pending_command = None
                context.verification_index += 1
                yield self._stable_event(
                    context,
                    "verification.completed",
                    self._verification_event_payload(
                        index,
                        pending or VerificationCommand(argv=()),
                        extra={"status": "rejected"},
                    ),
                    RecoveryStage.VERIFYING,
                )
            elif context.pending_command is not None:
                pending = context.pending_command
                index = context.verification_index
                result = self._verification_runner(context).run(pending)
                context.verification_failed = (
                    context.verification_failed or result.status != "passed"
                )
                context.pending_command = None
                context.verification_index += 1
                yield self._stable_event(
                    context,
                    "verification.completed",
                    self._verification_event_payload(index, pending, result),
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
        if request.kind == ApprovalKind.TOOL.value:
            pending_tool = context.pending_tool_action
            assert pending_tool is not None
            context.pending_tool_action = None
            call = ModelToolCall(
                call_id=pending_tool.call_id,
                name=pending_tool.action.tool_name,
                arguments=dict(pending_tool.action.normalized_arguments),
            )
            if decision == "reject":
                yield from self._emit_tool_result(
                    context,
                    call,
                    ToolResult(ok=False, error_code="approval_rejected"),
                )
                context.machine.transition(RunState.DISCOVERING)
                yield self._stable_event(
                    context,
                    "tool.action_resolved",
                    {"action_id": pending_tool.action.action_id, "status": "rejected"},
                    RecoveryStage.STARTED,
                )
                for output in self._drive(context):
                    if isinstance(output, EventEnvelope):
                        yield output
                return
            executor = self._tool_executor(context)
            implementation = executor.registry.implementation(pending_tool.action.tool_name)
            if implementation is None:
                yield from self._expire_approval(
                    context,
                    command,
                    "unknown_tool",
                    approval_id=request.approval_id,
                )
                return
            try:
                parsed = implementation.input_model.model_validate(
                    dict(pending_tool.action.normalized_arguments)
                )
                current_facts = executor._risk_facts(implementation, parsed)
            except Exception:
                yield from self._expire_approval(
                    context,
                    command,
                    "tool_fact_changed",
                    approval_id=request.approval_id,
                )
                return
            if executor.policy_engine.policy_hash != request.policy_hash:
                yield from self._expire_approval(
                    context,
                    command,
                    "policy_changed",
                    approval_id=request.approval_id,
                )
                return
            prepared = PreparedToolAction(
                action=pending_tool.action,
                definition=pending_tool.definition,
                parsed_arguments=parsed,
                policy_decision=pending_tool.policy_decision,
                target_facts_hash=pending_tool.target_facts_hash,
            )
            if executor.facts_hash(current_facts) != pending_tool.target_facts_hash:
                yield from self._expire_approval(
                    context,
                    command,
                    "tool_fact_changed",
                    approval_id=request.approval_id,
                )
                return
            tool_result = executor.execute_allowed(prepared, approved=True)
            yield from self._emit_tool_result(context, call, tool_result)
            context.machine.transition(RunState.DISCOVERING)
            yield self._stable_event(
                context,
                "tool.action_resolved",
                {
                    "action_id": pending_tool.action.action_id,
                    "status": "completed" if tool_result.ok else "failed",
                    "error_code": tool_result.error_code,
                },
                RecoveryStage.STARTED,
            )
            for output in self._drive(context):
                if isinstance(output, EventEnvelope):
                    yield output
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
                {
                    "status": apply_result.status.value,
                    "paths": list(apply_result.paths),
                    "written": apply_result.written,
                    "rollbackable": apply_result.rollbackable,
                    "next_step": apply_result.next_step,
                    "error_code": apply_result.error_code,
                },
            )
            yield from self._fail(context, apply_result.error_code or apply_result.status.value)
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
        signature = f"{call.name}:{call.arguments}"
        if context.last_tool_signature == signature:
            context.repeated_tool_streak += 1
        else:
            context.last_tool_signature = signature
            context.repeated_tool_streak = 1
        if context.repeated_tool_streak >= 3:
            yield from self._fail(context, "repeated_tool_call")
            return
        started: dict[str, Any] = {"name": call.name, "call_id": call.call_id}
        target = tool_call_target(call)
        if target:
            started["target"] = target
        yield self._event(context, "tool.started", started)
        if call.parse_error:
            yield from self._reject_tool(
                context,
                call,
                {
                    "error": call.parse_error,
                    "reason_code": call.parse_error,
                    "suggestion": "resend the tool call as a single complete JSON object",
                },
            )
            return
        if call.name == "propose_changeset":
            yield from self._propose(context, call)
            return
        executor = self._tool_executor(context)
        try:
            prepared = executor.prepare(
                run_id=context.run_id, name=call.name, arguments=call.arguments
            )
        except ToolPreparationError as exc:
            yield from self._reject_tool(
                context, call, {"error": exc.error_code, "reason_code": exc.error_code}
            )
            return
        yield self._event(
            context,
            "tool.policy_decided",
            {
                "action_id": prepared.action.action_id,
                "name": prepared.action.tool_name,
                "decision": prepared.policy_decision.decision.value,
                "policy_hash": prepared.policy_decision.policy_hash,
            },
        )
        yield self._event(
            context,
            "tool.action_prepared",
            {
                "action_id": prepared.action.action_id,
                "input_hash": prepared.action.input_hash,
                "target_facts_hash": prepared.target_facts_hash,
                "name": prepared.action.tool_name,
            },
        )
        if prepared.policy_decision.decision.value == "approval_required":
            context.pending_tool_action = PersistedToolAction(
                call_id=call.call_id,
                action=prepared.action,
                definition=prepared.definition,
                policy_decision=prepared.policy_decision,
                target_facts_hash=prepared.target_facts_hash,
            )
            context.machine.transition(RunState.AWAITING_APPROVAL)
            request = context.approval_gate.require(
                ApprovalKind.TOOL,
                prepared.action.action_id,
                prepared.action.input_hash,
                f"execute tool {prepared.action.tool_name}",
                "high",
                workspace_identity=prepared.action.workspace_identity,
                policy_hash=prepared.policy_decision.policy_hash,
                fact_hash=prepared.target_facts_hash,
                **self._security_approval_kwargs(context),
            )
            yield self._stable_event(
                context,
                "approval.required",
                self._approval_payload(request, context),
                RecoveryStage.AWAITING_TOOL_APPROVAL,
            )
            return
        result = executor.execute_allowed(prepared)
        yield from self._emit_tool_result(context, call, result)

    def _emit_tool_result(
        self, context: RunContext, call: ModelToolCall, result: ToolResult
    ) -> Iterator[EventEnvelope]:
        target = tool_call_target(call)
        origin = call.name
        source_kind = "tool_output"
        if isinstance(call.arguments, dict) and call.arguments.get("path") is not None:
            relative = str(call.arguments.get("path"))
            origin = f"{call.name}:{relative}"
            if call.name in {"read", "read_file"}:
                source_kind = source_kind_for_path(relative)
        if result.content is None:
            text = ""
        else:
            text = json.dumps(result.content, ensure_ascii=False, sort_keys=True)
        envelope, rendered, events = self._prepare_content(
            context,
            text,
            source_kind=source_kind,
            origin=origin,
            truncated=bool(result.truncated),
        )
        yield from events
        payload = {
            "name": call.name,
            "call_id": call.call_id,
            "ok": result.ok,
            "truncated": result.truncated,
            "error_code": result.error_code,
            "source_kind": envelope.source_kind,
            "trust_level": envelope.trust_level.value,
            "content_hash": envelope.content_hash,
        }
        if target:
            payload["target"] = target
        yield self._event(context, "tool.completed", payload)
        tool_text = tool_result_message(call, result, rendered)
        context.messages.append(
            ModelMessage(role="tool", content=tool_text, tool_call_id=call.call_id)
        )
        context.context_bytes = sum(
            len(message.content.encode("utf-8")) for message in context.messages
        )

    def _complete_with_retry(
        self, context: RunContext, request: ModelRequest
    ) -> Iterator[EventEnvelope | StreamFrame | ModelTurn | None]:
        # The Runtime protocol remains tool-capable even while a compatibility
        # fixture has an empty registry; providers must reject that mismatch
        # before receiving a request.
        has_tools = True
        if not self.adapter.capabilities.supports_request(has_tools=has_tools):
            error = ModelProviderError(
                ModelErrorCode.CAPABILITY_MISMATCH,
                "model capabilities do not support this request",
            )
            yield self._event(context, "model.failed", safe_error_payload(error, 0))
            yield None
            return
        stream_id = f"stream_{uuid4().hex}"
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            yield self._event(
                context,
                "model.requested",
                {"turn": context.model_turns, "attempt": attempt},
            )
            started = datetime.now(UTC)
            frame_index = 0
            try:
                turn: ModelTurn | None = None
                for item in self.adapter.stream(request):
                    if isinstance(item, ModelTextDelta):
                        yield StreamFrame(
                            run_id=context.run_id,
                            stream_id=stream_id,
                            index=frame_index,
                            type=StreamFrameType.ASSISTANT_DELTA,
                            payload={"text": item.text},
                        )
                        frame_index += 1
                    elif isinstance(item, ModelStreamCompleted):
                        turn = item.turn
                if turn is None:
                    raise ModelProviderError(
                        ModelErrorCode.INVALID_RESPONSE,
                        "provider stream missing completion",
                    )
            except ModelProviderError as provider_error:
                if not self.retry_policy.should_retry(provider_error, attempt):
                    yield self._event(
                        context, "model.failed", safe_error_payload(provider_error, attempt)
                    )
                    yield None
                    return
                delay = self.retry_policy.delay_seconds(provider_error, attempt)
                yield self._event(
                    context,
                    "model.retrying",
                    {
                        "attempt": attempt,
                        "delay": delay,
                        "code": provider_error.code.value,
                    },
                )
                self.sleep(delay)
                continue
            except Exception:
                mapped = ModelProviderError(ModelErrorCode.SERVICE, "provider request failed")
                yield self._event(context, "model.failed", safe_error_payload(mapped, attempt))
                yield None
                return
            duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            usage = None
            if turn.usage is not None:
                usage = turn.usage.model_dump(mode="json")
            yield self._event(
                context,
                "model.completed",
                {
                    "finish_reason": turn.finish_reason,
                    "tool_call_count": len(turn.tool_calls),
                    "attempt": attempt,
                    "usage": usage,
                    "request_id": turn.provider_request_id,
                    "duration_ms": duration_ms,
                    "stream_id": stream_id,
                },
            )
            yield turn
            return
        yield None

    def _drive(self, context: RunContext) -> Iterator[RuntimeOutput]:
        halt = {
            RunState.AWAITING_APPROVAL,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.COMPLETED,
            RunState.VERIFICATION_FAILED,
            RunState.STALE,
        }
        while context.machine.state not in halt:
            if context.model_turns >= self.limits.max_model_turns:
                yield from self._fail(context, "max_model_turns")
                return
            if context.context_bytes >= self.limits.max_context_bytes:
                context.messages = compact_run_messages(
                    context.messages,
                    max_bytes=self.limits.max_context_bytes,
                )
                context.context_bytes = sum(
                    len(message.content.encode("utf-8")) for message in context.messages
                )
            if context.context_bytes >= self.limits.max_context_bytes:
                yield from self._fail(context, "max_context_bytes")
                return
            context.model_turns += 1
            request = self._model_request(context)
            turn: ModelTurn | None = None
            for item in self._complete_with_retry(context, request):
                if isinstance(item, (EventEnvelope, StreamFrame)):
                    yield item
                else:
                    turn = item
            if context.machine.state == RunState.CANCELLED:
                return
            if turn is None:
                yield from self._fail(context, "model_error")
                return
            context.messages.append(
                ModelMessage(
                    role="assistant",
                    content=turn.assistant_text or "",
                    tool_calls=turn.tool_calls,
                    reasoning_content=turn.reasoning_content,
                )
            )
            if turn.assistant_text:
                _envelope, _rendered, flagged = self._prepare_content(
                    context,
                    turn.assistant_text,
                    source_kind="model_output",
                    origin="model.assistant",
                )
                yield from flagged
            if not turn.tool_calls:
                text = (turn.assistant_text or "").strip()
                if not text:
                    if context.tool_calls > 0 and not context.empty_after_tools_nudge:
                        context.empty_after_tools_nudge = True
                        context.messages.append(
                            ModelMessage(role="user", content=_EMPTY_AFTER_TOOLS_NUDGE)
                        )
                        continue
                    yield from self._fail(context, "empty_model_response")
                    return
                if claims_unissued_changeset(text) and not context.claimed_changeset_nudge:
                    context.claimed_changeset_nudge = True
                    context.messages.append(ModelMessage(role="assistant", content=text))
                    context.messages.append(
                        ModelMessage(role="user", content=_CLAIMED_CHANGESET_NUDGE)
                    )
                    continue
                context.machine.transition(RunState.COMPLETED)
                yield self._event(
                    context,
                    "assistant.message",
                    {
                        "content": text,
                        "stream_id": next(
                            (
                                event.payload.get("stream_id")
                                for event in reversed(context.journal.read_all())
                                if event.type == "model.completed"
                            ),
                            None,
                        ),
                    },
                )
                yield self._stable_event(
                    context,
                    "run.completed",
                    {"state": RunState.COMPLETED.value, "outcome": "responded"},
                    RecoveryStage.TERMINAL,
                )
                return
            context.machine.transition(RunState.GENERATING)
            pending = list(turn.tool_calls)
            for index, call in enumerate(pending):
                if context.tool_calls >= self.limits.max_tool_calls:
                    for skipped in pending[index:]:
                        context.messages.append(
                            ModelMessage(
                                role="tool",
                                content=_TOOL_LIMIT_SKIPPED,
                                tool_call_id=skipped.call_id,
                            )
                        )
                    yield from self._finish_at_tool_limit(context)
                    return
                context.tool_calls += 1
                encoded = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)
                _envelope, _rendered, flagged = self._prepare_content(
                    context,
                    encoded,
                    source_kind="model_output",
                    origin=f"model.tool_call:{call.name}",
                )
                yield from flagged
                yield from self._execute_tool(context, call)
                if context.machine.state in {
                    RunState.AWAITING_APPROVAL,
                    RunState.FAILED,
                    RunState.CANCELLED,
                }:
                    return
            context.messages = compact_run_messages(
                context.messages,
                max_bytes=self.limits.max_context_bytes,
            )
            context.context_bytes = sum(
                len(message.content.encode("utf-8")) for message in context.messages
            )
            context.machine.transition(RunState.DISCOVERING)

    def _finish_at_tool_limit(self, context: RunContext) -> Iterator[RuntimeOutput]:
        if context.workspace_write_started or context.built_change_set is not None:
            yield from self._fail(context, "max_tool_calls")
            return
        if context.model_turns >= self.limits.max_model_turns:
            yield from self._fail(context, "max_tool_calls")
            return
        context.messages.append(ModelMessage(role="user", content=_TOOL_LIMIT_WRAP_UP))
        context.model_turns += 1
        request = ModelRequest(
            messages=tuple(context.messages),
            tools=(),
            max_output_tokens=4_096,
        )
        turn: ModelTurn | None = None
        for item in self._complete_with_retry(context, request):
            if isinstance(item, (EventEnvelope, StreamFrame)):
                yield item
            else:
                turn = item
        if turn is None or turn.tool_calls:
            yield from self._fail(context, "max_tool_calls")
            return
        text = (turn.assistant_text or "").strip()
        if not text:
            yield from self._fail(context, "max_tool_calls")
            return
        context.messages.append(
            ModelMessage(
                role="assistant",
                content=text,
                reasoning_content=turn.reasoning_content,
            )
        )
        context.machine.transition(RunState.DISCOVERING)
        context.machine.transition(RunState.COMPLETED)
        yield self._event(context, "assistant.message", {"content": text})
        yield self._stable_event(
            context,
            "run.completed",
            {"state": RunState.COMPLETED.value, "outcome": "responded"},
            RecoveryStage.TERMINAL,
        )

    def _compact(self, context: RunContext) -> Iterator[RuntimeOutput]:
        request = ModelRequest(
            messages=tuple(context.messages),
            tools=(),
            max_output_tokens=4_096,
        )
        turn: ModelTurn | None = None
        for item in self._complete_with_retry(context, request):
            if isinstance(item, (EventEnvelope, StreamFrame)):
                yield item
            else:
                turn = item
        if turn is None:
            yield from self._fail(context, "model_error")
            return
        if turn.tool_calls:
            yield from self._fail(context, "invalid_compaction_response")
            return
        text = (turn.assistant_text or "").strip()
        if not text:
            yield from self._fail(context, "empty_model_response")
            return
        context.machine.transition(RunState.COMPLETED)
        _envelope, _rendered, flagged = self._prepare_content(
            context,
            text,
            source_kind="conversation_summary",
            origin="conversation.compacted",
        )
        yield from flagged
        yield self._event(context, "conversation.compacted", {"summary": text})
        yield self._event(
            context,
            "run.completed",
            {"state": RunState.COMPLETED.value, "outcome": "compacted"},
        )

    def handle(self, command: CoreCommand) -> Iterator[EventEnvelope]:
        for output in self.stream(command):
            if isinstance(output, EventEnvelope):
                yield output

    def stream(self, command: CoreCommand) -> Iterator[RuntimeOutput]:
        try:
            yield from self._dispatch(command)
        except SnapshotPersistError as exc:
            yield exc.failed_event

    def _dispatch(self, command: CoreCommand) -> Iterator[RuntimeOutput]:
        if isinstance(command, CancelRun):

            def _cancel_once() -> Iterator[EventEnvelope]:
                context = self.runs.get(command.run_id)
                if context is None:
                    return
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

            yield from self._with_receipt(
                "cancel",
                command.run_id,
                {"run_id": command.run_id},
                _cancel_once(),
            )
            return
        if isinstance(command, ResolveApproval):
            yield from self._with_receipt(
                "resolve_approval",
                command.run_id,
                {
                    "run_id": command.run_id,
                    "approval_id": command.approval_id,
                    "target_hash": command.target_hash,
                    "decision": command.decision,
                },
                self._resolve_approval(command),
                extra_refs=lambda: self._file_effect_refs(command.run_id),
            )
            return
        if isinstance(command, RollbackRun):
            if command.run_id is None:
                yield from self._rollback(command)
                return
            rollback_run_id = command.run_id
            yield from self._with_receipt(
                "rollback",
                rollback_run_id,
                {"run_id": rollback_run_id, "checkpoint_id": command.checkpoint_id},
                self._rollback(command),
                extra_refs=lambda: self._file_effect_refs(rollback_run_id),
            )
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
            payload = {"run_id": command.run_id}
            operation_id, _input_hash = receipt_key("resume", payload)
            existing_receipt = self.receipts.load(command.run_id, operation_id)
            if existing_receipt is not None and command.run_id not in self.runs:
                with suppress(Exception):
                    self.runs[command.run_id] = RunResumer(self.coordinator).load_context(
                        command.run_id
                    )
            collected: list[EventEnvelope] = []
            for event in self._resume(command):
                collected.append(event)
                yield event
            if existing_receipt is None:
                self._commit_receipt(
                    operation="resume",
                    run_id=command.run_id,
                    payload=payload,
                    events=collected,
                )
            return
        if isinstance(command, AbandonRun):
            yield from self._abandon(command)
            return
        if not isinstance(command, StartRun):
            return
        run_id = f"run_{uuid4().hex}"
        kind = "compaction" if command.mode == "compact" else "task"
        self._bind_default_policy_to_workspace(command.workspace_root)
        goal_envelope = build_content_envelope(
            command.goal, source_kind="user_goal", origin="start_run.goal"
        )
        context = RunContext(
            run_id=run_id,
            command=command,
            machine=RunStateMachine(),
            journal=EventJournal(self.state_dir, run_id, Redactor([])),
            messages=[],
            approval_gate=ApprovalGate(run_id),
            security_context_hash=EMPTY_SECURITY_CONTEXT_HASH,
        )
        self.runs[run_id] = context
        context.machine.transition(RunState.DISCOVERING)
        yield self._stable_event(
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
        yield from self._seed_context(context)
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
        self._bind_default_policy_to_workspace(context.command.workspace_root)
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
                **self._security_approval_kwargs(context),
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
