"""Narrow host contracts shared by Runtime flow modules."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from vera.config import Limits
from vera.content.detector import SafeContentDetector
from vera.content.envelope import ContentEnvelope
from vera.content.trust import ContentTrustLevel
from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import ResolveApproval
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryReport, RecoveryStage
from vera.contracts.streaming import RuntimeOutput, StreamFrame
from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.models.base import ModelRequest, ModelTurn
from vera.models.retry import RetryPolicy
from vera.persistence.operation_receipt import OperationReceiptStore
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.policy.engine import PolicyEngine
from vera.project_instructions import ProjectInstructionService
from vera.recovery.coordinator import RecoveryCoordinator
from vera.runtime.context import RunContext
from vera.tools.command_policy import CommandPolicy
from vera.tools.definitions import ToolResult
from vera.tools.executor import PreparedToolAction, ToolExecutor
from vera.verification.artifacts import VerificationArtifactPlanner
from vera.verification.runner import VerificationRunner
from vera.workspace.apply import FileWriter


class ContentFlowHost(Protocol):
    """Only the Runtime state needed by content/context flows."""

    content_detector: SafeContentDetector
    project_instructions: ProjectInstructionService

    def _seed_skill_context(self, context: RunContext) -> Iterator[EventEnvelope]: ...

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope: ...


class ToolFlowHost(Protocol):
    """Runtime state and stable callbacks required by tool flows."""

    state_dir: Path
    runs: dict[str, RunContext]
    receipts: OperationReceiptStore
    coordinator: RecoveryCoordinator

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope: ...

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope: ...

    def _prepare_content(
        self,
        context: RunContext,
        text: str,
        *,
        source_kind: str | None,
        origin: str,
        truncated: bool = False,
        trust_level: ContentTrustLevel | None = None,
    ) -> tuple[ContentEnvelope, str, list[EventEnvelope]]: ...


class VerificationFlowHost(Protocol):
    """Runtime state and callbacks required by verification flows."""

    artifact_prefix: Path | None
    installation_id: str
    command_policy: CommandPolicy
    policy_engine: PolicyEngine

    def _planner(self) -> VerificationArtifactPlanner: ...

    def _verification_runner(self, context: RunContext) -> VerificationRunner: ...

    def _verification_binding_matches(
        self, context: RunContext, command: VerificationCommand, index: int
    ) -> bool: ...

    def _expected_artifact_root(self, context: RunContext, index: int) -> Path: ...

    def _verification_event_payload(
        self,
        index: int,
        command: VerificationCommand,
        result: VerificationResult | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def _policy_binding(self, root: Path) -> tuple[str, str]: ...

    def _security_approval_kwargs(self, context: RunContext) -> dict[str, Any]: ...

    def _approval_payload(
        self, request: ApprovalRequest, context: RunContext | None = None
    ) -> dict[str, Any]: ...

    def _fail(self, context: RunContext, reason: str) -> Any: ...

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope: ...


class ApprovalFlowHost(Protocol):
    """Runtime state and callbacks required by proposal/approval flows."""

    runs: dict[str, RunContext]
    state_dir: Path
    file_writer: FileWriter | None
    project_instructions: ProjectInstructionService
    policy_engine: PolicyEngine
    command_policy: CommandPolicy
    coordinator: RecoveryCoordinator

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope: ...

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope: ...

    def _fail(self, context: RunContext, reason: str) -> Iterator[EventEnvelope]: ...

    def _reject_tool(
        self, context: RunContext, call: Any, payload: dict[str, Any]
    ) -> Iterator[EventEnvelope]: ...

    def _plan_verification(
        self,
        context: RunContext,
        commands: Sequence[VerificationCommand],
    ) -> tuple[VerificationCommand, ...]: ...

    def _policy_binding(self, root: Path) -> tuple[str, str]: ...

    def _security_approval_kwargs(self, context: RunContext) -> dict[str, Any]: ...

    def _approval_payload(
        self, request: ApprovalRequest, context: RunContext | None = None
    ) -> dict[str, Any]: ...

    def _expire_approval(
        self,
        context: RunContext | None,
        command: ResolveApproval,
        reason: str,
        approval_id: str | None = None,
    ) -> Iterator[EventEnvelope]: ...

    def _verification_binding_matches(
        self, context: RunContext, command: VerificationCommand, index: int
    ) -> bool: ...

    def _verification_event_payload(
        self,
        index: int,
        command: VerificationCommand,
        result: VerificationResult | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def _verification_runner(self, context: RunContext) -> VerificationRunner: ...

    def _verify(self, context: RunContext) -> Iterator[EventEnvelope]: ...

    def _report_payload(self, report: RecoveryReport) -> dict[str, Any]: ...

    def _apply_recovery_plan(
        self, context: RunContext, request: ApprovalRequest
    ) -> Iterator[EventEnvelope]: ...

    def _emit_tool_result(
        self, context: RunContext, call: Any, result: ToolResult
    ) -> Iterator[EventEnvelope]: ...

    def _drive(self, context: RunContext) -> Iterator[RuntimeOutput]: ...

    def _tool_executor(self, context: RunContext) -> ToolExecutor: ...

    @staticmethod
    def _available_tool_scopes(
        prepared: PreparedToolAction,
    ) -> tuple[Literal["once", "run", "workspace"], ...]: ...

    def _execute_prepared_tool(
        self,
        context: RunContext,
        call: Any,
        executor: ToolExecutor,
        prepared: PreparedToolAction,
        *,
        approved: bool = False,
    ) -> tuple[ToolResult, tuple[EventEnvelope, ...]]: ...


class LoopFlowHost(Protocol):
    """Runtime state and callbacks required by the model loop."""

    adapter: Any
    retry_policy: RetryPolicy
    sleep: Callable[[float], None]
    limits: Limits

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope: ...

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope: ...

    def _fail(self, context: RunContext, reason: str) -> Iterator[EventEnvelope]: ...

    def _reject_tool(
        self, context: RunContext, call: Any, payload: dict[str, Any]
    ) -> Iterator[EventEnvelope]: ...

    def _propose(self, context: RunContext, call: Any) -> Iterator[EventEnvelope]: ...

    def _tool_executor(self, context: RunContext) -> ToolExecutor: ...

    @staticmethod
    def _available_tool_scopes(
        prepared: PreparedToolAction,
    ) -> tuple[Literal["once", "run", "workspace"], ...]: ...

    def _security_approval_kwargs(self, context: RunContext) -> dict[str, Any]: ...

    def _approval_payload(
        self, request: ApprovalRequest, context: RunContext | None = None
    ) -> dict[str, Any]: ...

    def _execute_prepared_tool(
        self,
        context: RunContext,
        call: Any,
        executor: ToolExecutor,
        prepared: PreparedToolAction,
        *,
        approved: bool = False,
    ) -> tuple[ToolResult, tuple[EventEnvelope, ...]]: ...

    def _model_request(self, context: RunContext) -> ModelRequest: ...

    def _complete_with_retry(
        self, context: RunContext, request: ModelRequest
    ) -> Iterator[EventEnvelope | StreamFrame | ModelTurn | None]: ...

    def _prepare_content(
        self,
        context: RunContext,
        text: str,
        *,
        source_kind: str | None,
        origin: str,
        truncated: bool = False,
    ) -> tuple[ContentEnvelope, str, list[EventEnvelope]]: ...

    def _execute_tool(self, context: RunContext, call: Any) -> Iterator[EventEnvelope]: ...

    def _finish_at_tool_limit(self, context: RunContext) -> Iterator[RuntimeOutput]: ...


class CommandFlowHost(Protocol):
    """Runtime state and callbacks required by command dispatch."""

    state_dir: Path
    runs: dict[str, RunContext]
    snapshot_store: Any
    coordinator: RecoveryCoordinator
    receipts: OperationReceiptStore

    def _ephemeral_event(
        self, run_id: str, event_type: str, payload: dict[str, Any], sequence: int = 1
    ) -> EventEnvelope: ...

    def _with_receipt(
        self,
        operation: Literal["resume", "resolve_approval", "cancel", "rollback"],
        run_id: str,
        payload: dict[str, Any],
        events: Iterator[EventEnvelope],
        *,
        extra_refs: Callable[[], tuple[str, ...]] | None = None,
        hydrate: bool = False,
    ) -> Iterator[EventEnvelope]: ...

    def _resolve_approval(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _file_effect_refs(self, run_id: str) -> tuple[str, ...]: ...

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
    ) -> None: ...

    def _rollback(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _inspect_recovery(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _inspect_state(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _plan_state_migration(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _apply_state_migration(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _resume(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _abandon(self, command: Any) -> Iterator[EventEnvelope]: ...

    def _bind_default_policy_to_workspace(self, root: Path) -> None: ...

    def _bind_skill_snapshot(self, context: RunContext) -> bool: ...

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope: ...

    def _seed_context(self, context: RunContext) -> Iterator[EventEnvelope]: ...

    def _compact(self, context: RunContext) -> Iterator[RuntimeOutput]: ...

    def _drive(self, context: RunContext) -> Iterator[RuntimeOutput]: ...


class RecoveryFlowHost(Protocol):
    """Runtime state and callbacks required by recovery flows."""

    runs: dict[str, RunContext]
    state_dir: Path
    snapshot_store: Any
    coordinator: RecoveryCoordinator
    file_writer: FileWriter | None
    policy_engine: PolicyEngine

    def _restore_skill_snapshot(self, context: RunContext, snapshot: Any) -> RunContext: ...

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope: ...

    def _stable_event(
        self,
        context: RunContext,
        event_type: str,
        payload: dict[str, Any],
        stage: RecoveryStage,
    ) -> EventEnvelope: ...

    def _fail(self, context: RunContext, reason: str) -> Iterator[EventEnvelope]: ...

    def _ephemeral_event(
        self, run_id: str, event_type: str, payload: dict[str, Any], sequence: int = 1
    ) -> EventEnvelope: ...

    def _report_payload(self, report: RecoveryReport) -> dict[str, Any]: ...

    def _approval_payload(
        self, request: ApprovalRequest, context: RunContext | None = None
    ) -> dict[str, Any]: ...

    def _reject_resume(self, report: RecoveryReport) -> Iterator[EventEnvelope]: ...

    def _bind_default_policy_to_workspace(self, root: Path) -> None: ...

    def _propose_partial_restore(
        self, context: RunContext, report: RecoveryReport
    ) -> Iterator[EventEnvelope]: ...

    def _verify(self, context: RunContext) -> Iterator[EventEnvelope]: ...

    def _policy_binding(self, root: Path) -> tuple[str, str]: ...

    def _security_approval_kwargs(self, context: RunContext) -> dict[str, Any]: ...

    def _apply_recovery_plan(
        self, context: RunContext, request: ApprovalRequest
    ) -> Iterator[EventEnvelope]: ...

    def _context_from_snapshot(self, run_id: str) -> RunContext: ...


class SnapshotFlowHost(Protocol):
    """Runtime state and callbacks needed to persist stable snapshots."""

    installation_id: str
    snapshot_store: RecoverySnapshotStore

    def _should_snapshot(self, context: RunContext) -> bool: ...

    def _event(
        self, context: RunContext, event_type: str, payload: dict[str, Any]
    ) -> EventEnvelope: ...
