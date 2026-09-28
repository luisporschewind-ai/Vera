"""Bounded discovery loop that stops before any filesystem mutation."""

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import suppress
from pathlib import Path
from time import sleep as default_sleep
from typing import Any, Literal

from vera.config import Limits
from vera.content.detector import (
    BaselinePromptInjectionDetector,
    ContentDetector,
    SafeContentDetector,
)
from vera.content.envelope import (
    EMPTY_SECURITY_CONTEXT_HASH,
)
from vera.content.trust import ContentTrustLevel
from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import (
    AbandonRun,
    ApplyStateMigration,
    CoreCommand,
    InspectRecovery,
    InspectState,
    PlanStateMigration,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
)
from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryReport, RecoveryStage
from vera.contracts.streaming import RuntimeOutput, StreamFrame
from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.models.base import ModelAdapter, ModelMessage, ModelRequest, ModelToolCall, ModelTurn
from vera.models.retry import RetryPolicy
from vera.persistence.operation_receipt import OperationReceipt, OperationReceiptStore
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.process.supervisor import ProcessSupervisor
from vera.project_instructions import ProjectInstructionService
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.models import RecoverySnapshot
from vera.recovery.probe import workspace_identity
from vera.runtime.approval_flow import ApprovalFlow
from vera.runtime.command_flow import CommandFlow
from vera.runtime.content_flow import (
    append_conversation_message as append_conversation_message_flow,
)
from vera.runtime.content_flow import (
    prepare_content as prepare_content_flow,
)
from vera.runtime.content_flow import (
    record_finding as record_finding_flow,
)
from vera.runtime.content_flow import (
    seed_context as seed_context_flow,
)
from vera.runtime.content_flow import (
    seed_project_instructions as seed_project_instructions_flow,
)
from vera.runtime.context import RunContext, tool_result_message
from vera.runtime.intake import (
    ProposalInput,  # noqa: F401 - preserve the legacy public import
    SnapshotPersistError,
    claims_unissued_changeset,  # noqa: F401 - preserve the legacy public import
    tool_call_target,
)
from vera.runtime.loop_flow import LoopFlow
from vera.runtime.recovery_flow import RecoveryFlow
from vera.runtime.security import (
    collected_risk_labels,
)
from vera.runtime.skills_flow import SkillsFlow
from vera.runtime.snapshot_flow import SnapshotFlow
from vera.runtime.state import RunState
from vera.runtime.tool_flow import (
    ToolExecutionFlow,
)
from vera.runtime.tool_flow import (
    available_tool_scopes as available_tool_scopes_flow,
)
from vera.runtime.tool_flow import (
    commit_receipt as commit_receipt_flow,
)
from vera.runtime.tool_flow import (
    file_effect_refs as file_effect_refs_flow,
)
from vera.runtime.tool_flow import (
    replay_receipt as replay_receipt_flow,
)
from vera.runtime.tool_flow import (
    with_receipt as with_receipt_flow,
)
from vera.runtime.verification_flow import VerificationFlow
from vera.sandbox.access import AccessSession
from vera.skills.context import SkillContextAssembler
from vera.skills.selection import SkillSelectionService
from vera.skills.snapshot_store import SkillSnapshotStore
from vera.tools.command_policy import CommandPolicy
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.executor import PreparedToolAction, ToolExecutor
from vera.tools.registry import ToolRegistry
from vera.verification.artifacts import (
    VerificationArtifactPlanner,
)
from vera.verification.runner import VerificationRunner
from vera.workspace.apply import FileWriter


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
        access_session: AccessSession | None = None,
        process_supervisor: ProcessSupervisor | None = None,
        skill_selection_service: SkillSelectionService | None = None,
        skill_snapshot_store: SkillSnapshotStore | None = None,
        skill_context_assembler: SkillContextAssembler | None = None,
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
        self.access_session = access_session
        self.process_supervisor = process_supervisor
        self.skill_selection_service = skill_selection_service
        self.skill_snapshot_store = skill_snapshot_store or SkillSnapshotStore()
        self.skill_context_assembler = skill_context_assembler or SkillContextAssembler()
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
            state_dir=self.state_dir,
            access_session=self.access_session,
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
        trust_level: ContentTrustLevel | None = None,
    ) -> tuple[Any, str, list[EventEnvelope]]:
        return prepare_content_flow(
            self,
            context,
            text,
            source_kind=source_kind,
            origin=origin,
            truncated=truncated,
            trust_level=trust_level,
        )

    def _record_finding(
        self, context: RunContext, envelope: Any, detection: Any
    ) -> list[EventEnvelope]:
        return record_finding_flow(self, context, envelope, detection)

    def _seed_context(self, context: RunContext) -> Iterator[EventEnvelope]:
        yield from seed_context_flow(self, context)

    def _bind_skill_snapshot(self, context: RunContext) -> bool:
        return SkillsFlow.bind(self, context)

    def _seed_skill_context(self, context: RunContext) -> Iterator[EventEnvelope]:
        yield from SkillsFlow.seed(self, context)

    def _restore_skill_snapshot(
        self, context: RunContext, snapshot: RecoverySnapshot
    ) -> RunContext:
        return SkillsFlow.restore(self, context, snapshot)

    def _seed_project_instructions(self, context: RunContext) -> Iterator[EventEnvelope]:
        yield from seed_project_instructions_flow(self, context)

    def _append_conversation_message(
        self, context: RunContext, message: ConversationMessage
    ) -> Iterator[EventEnvelope]:
        yield from append_conversation_message_flow(self, context, message)

    def _approval_payload(
        self, request: ApprovalRequest, context: RunContext | None = None
    ) -> dict[str, Any]:
        return ApprovalFlow.approval_payload(self, request, context)

    @staticmethod
    def _available_tool_scopes(
        prepared: PreparedToolAction,
    ) -> tuple[Literal["once", "run", "workspace"], ...]:
        return available_tool_scopes_flow(prepared)

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope:
        return context.journal.append(event_type, payload)

    def _replay_receipt(self, receipt: OperationReceipt) -> Iterator[EventEnvelope]:
        yield from replay_receipt_flow(self, receipt)

    def _file_effect_refs(self, run_id: str) -> tuple[str, ...]:
        return file_effect_refs_flow(self, run_id)

    def _commit_receipt(
        self,
        *,
        operation: Literal[
            "resume",
            "resolve_approval",
            "cancel",
            "rollback",
            "process",
            "git_commit",
            "git_branch",
        ],
        run_id: str,
        payload: dict[str, Any],
        events: Sequence[EventEnvelope],
        extra_refs: tuple[str, ...] = (),
    ) -> None:
        commit_receipt_flow(
            self,
            operation=operation,
            run_id=run_id,
            payload=payload,
            events=events,
            extra_refs=extra_refs,
        )

    @staticmethod
    def _process_receipt_payload(prepared: PreparedToolAction) -> dict[str, str]:
        return ToolExecutionFlow.process_receipt_payload(prepared)

    @staticmethod
    def _replayed_tool_result(events: Sequence[EventEnvelope]) -> ToolResult:
        return ToolExecutionFlow.replayed_tool_result(events)

    def _execute_prepared_tool(
        self,
        context: RunContext,
        call: ModelToolCall,
        executor: ToolExecutor,
        prepared: PreparedToolAction,
        *,
        approved: bool = False,
    ) -> tuple[ToolResult, tuple[EventEnvelope, ...]]:
        return ToolExecutionFlow.execute_prepared(
            self,
            context,
            call,
            executor,
            prepared,
            approved=approved,
        )

    @staticmethod
    def _git_operation_payload(prepared: PreparedToolAction) -> dict[str, Any]:
        return ToolExecutionFlow.git_operation_payload(prepared)

    def _execute_git_tool(
        self,
        context: RunContext,
        call: ModelToolCall,
        executor: ToolExecutor,
        prepared: PreparedToolAction,
        *,
        approved: bool,
    ) -> tuple[ToolResult, tuple[EventEnvelope, ...]]:
        return ToolExecutionFlow.execute_git(
            self,
            context,
            call,
            executor,
            prepared,
            approved=approved,
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
        yield from with_receipt_flow(
            self,
            operation,
            run_id,
            payload,
            events,
            extra_refs=extra_refs,
            hydrate=hydrate,
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
        return SnapshotFlow.snapshot_from_context(
            self,
            context,
            stage,
            sequence,
            verification_in_flight=verification_in_flight,
        )

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope:
        return SnapshotFlow.stable_event(self, context, event_type, payload, stage)

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
        return VerificationFlow.planner(self)

    def _verification_runner(self, context: RunContext) -> VerificationRunner:
        return VerificationFlow.verification_runner(self, context)

    def _plan_verification(
        self,
        context: RunContext,
        commands: Sequence[VerificationCommand],
    ) -> tuple[VerificationCommand, ...]:
        return VerificationFlow.plan(self, context, commands)

    def _expected_artifact_root(self, context: RunContext, index: int) -> Path:
        return VerificationFlow.expected_artifact_root(self, context, index)

    def _verification_binding_matches(
        self, context: RunContext, command: VerificationCommand, index: int
    ) -> bool:
        return VerificationFlow.binding_matches(self, context, command, index)

    def _verification_event_payload(
        self,
        index: int,
        command: VerificationCommand,
        result: VerificationResult | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return VerificationFlow.event_payload(self, index, command, result, extra)

    def _reject_tool(
        self, context: RunContext, call: ModelToolCall, payload: dict[str, Any]
    ) -> Iterator[EventEnvelope]:
        failed = {"name": call.name, "call_id": call.call_id, "ok": False, **payload}
        if context.active_tool_span_id is not None:
            failed["span_id"] = context.active_tool_span_id
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
        yield from ApprovalFlow.propose(self, context, call)

    def _verify(self, context: RunContext) -> Iterator[EventEnvelope]:
        yield from VerificationFlow.verify(self, context)

    def _expire_approval(
        self,
        context: RunContext | None,
        command: ResolveApproval,
        reason: str,
        approval_id: str | None = None,
    ) -> Iterator[EventEnvelope]:
        yield from ApprovalFlow.expire(self, context, command, reason, approval_id)

    def _resolve_approval(self, command: ResolveApproval) -> Iterator[EventEnvelope]:
        yield from ApprovalFlow.resolve(self, command)

    def _rollback(self, command: RollbackRun) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.rollback(self, command)

    def _execute_tool(self, context: RunContext, call: ModelToolCall) -> Iterator[EventEnvelope]:
        yield from LoopFlow.execute_tool(self, context, call)

    def _emit_tool_result(
        self, context: RunContext, call: ModelToolCall, result: ToolResult
    ) -> Iterator[EventEnvelope]:
        yield from ToolExecutionFlow.emit_tool_result(self, context, call, result)

    def _complete_with_retry(
        self, context: RunContext, request: ModelRequest
    ) -> Iterator[EventEnvelope | StreamFrame | ModelTurn | None]:
        yield from LoopFlow.complete_with_retry(self, context, request)

    def _drive(self, context: RunContext) -> Iterator[RuntimeOutput]:
        yield from LoopFlow.drive(self, context)

    def _finish_at_tool_limit(self, context: RunContext) -> Iterator[RuntimeOutput]:
        yield from LoopFlow.finish_at_tool_limit(self, context)

    def _compact(self, context: RunContext) -> Iterator[RuntimeOutput]:
        yield from LoopFlow.compact(self, context)

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
        yield from CommandFlow.dispatch(self, command)

    def _report_payload(self, report: RecoveryReport) -> dict[str, Any]:
        return RecoveryFlow.report_payload(self, report)

    def _ephemeral_event(
        self, run_id: str, event_type: str, payload: dict[str, Any], sequence: int = 1
    ) -> EventEnvelope:
        return RecoveryFlow.ephemeral_event(self, run_id, event_type, payload, sequence)

    def _inspect_recovery(self, command: InspectRecovery) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.inspect_recovery(self, command)

    def _inspect_state(self, command: InspectState) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.inspect_state(self, command)

    def _plan_state_migration(self, command: PlanStateMigration) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.plan_state_migration(self, command)

    def _apply_state_migration(self, command: ApplyStateMigration) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.apply_state_migration(self, command)

    def _reject_resume(self, report: RecoveryReport) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.reject_resume(self, report)

    def _resume(self, command: ResumeRun) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.resume(self, command)

    def _propose_partial_restore(
        self, context: RunContext, report: RecoveryReport
    ) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.propose_partial_restore(self, context, report)

    def _apply_recovery_plan(
        self, context: RunContext, request: ApprovalRequest
    ) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.apply_recovery_plan(self, context, request)

    def _context_from_snapshot(self, run_id: str) -> RunContext:
        return RecoveryFlow.context_from_snapshot(self, run_id)

    def _abandon(self, command: AbandonRun) -> Iterator[EventEnvelope]:
        yield from RecoveryFlow.abandon(self, command)
