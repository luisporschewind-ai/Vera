"""Proposal and approval lifecycle flows."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from vera.content.envelope import EMPTY_SECURITY_CONTEXT_HASH
from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import ResolveApproval
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelToolCall
from vera.runtime.approval import ApprovalKind, ApprovalMismatch
from vera.runtime.context import RunContext
from vera.runtime.flow_protocols import ApprovalFlowHost
from vera.runtime.intake import ProposalInput
from vera.runtime.state import RunState
from vera.runtime.verification_flow import (
    finish_verification_span,
    start_verification_span,
    verification_span_error,
)
from vera.sandbox.files import PermissionPaths
from vera.tools.definitions import ToolResult
from vera.tools.executor import PreparedToolAction
from vera.verification.artifacts import VerificationArtifactError
from vera.workspace.apply import ApplyStatus, ChangeApplier
from vera.workspace.changeset import ChangeSetBuilder
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


def approval_payload(
    host: ApprovalFlowHost, request: ApprovalRequest, context: RunContext | None = None
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
        "available_scopes": list(request.available_scopes),
    }
    if "apple_ios_build_services" in request.required_capabilities:
        from vera.sandbox.apple_volume import APPLE_BUILD_STORAGE

        payload["build_storage"] = dict(APPLE_BUILD_STORAGE)
        payload["system_service_grant"] = {
            "capability": "apple_ios_build_services",
            "scope": "once",
            "services": list(request.system_service_names),
            "inherited_by_descendants": True,
            "may_access_current_user_simulator_state": True,
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
        if pending.action.tool_name == "git_repository_init":
            workspace = str(context.command.workspace_root)
            branch = str(pending.action.normalized_arguments.get("initial_branch") or "main")
            payload["workspace"] = workspace
            payload["target"] = f"{workspace}/.git"
            payload["description"] = (
                f"在 {workspace} 初始化本地 Git 仓库（初始分支 {branch}）；"
                "只创建 .git 元数据，不创建提交、远程、身份或 Hook。"
            )
        elif pending.action.tool_name == "request_file_access":
            payload["file_access"] = dict(pending.action.normalized_arguments)
        elif pending.action.tool_name == "bash":
            arguments = pending.action.model_dump(mode="json")["normalized_arguments"]
            payload["argv"] = arguments.get("argv", [])
            payload["cwd"] = arguments.get("cwd", ".")
            payload["timeout_seconds"] = arguments.get("timeout_seconds")
    return payload


def propose(
    host: ApprovalFlowHost, context: RunContext, call: ModelToolCall
) -> Iterator[EventEnvelope]:
    try:
        proposal = ProposalInput.model_validate(call.arguments)
        invalid_init = context.command.mode == "project_init" and (
            len(proposal.changes) != 1
            or proposal.changes[0].path != "VERA.md"
            or proposal.changes[0].operation not in {"create", "update"}
            or proposal.verification
        )
        if invalid_init:
            yield from host._fail(context, "project_init_scope_violation")
            return
        planned = host._plan_verification(context, proposal.verification)
        paths = (
            PermissionPaths(host.access_session)
            if host.access_session is not None
            else WorkspacePaths(context.command.workspace_root)
        )
        built = ChangeSetBuilder(paths).build(
            context.run_id,
            proposal.summary,
            proposal.changes,
            planned,
        )
    except VerificationArtifactError as exc:
        yield from host._reject_tool(
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
            yield from host._fail(context, "project_init_scope_violation")
            return
        yield from host._reject_tool(context, call, {"error": str(exc)})
        return
    change_set = built.change_set
    if context.command.mode == "project_init":
        try:
            host.project_instructions.validate_init_changeset(change_set)
        except ValueError:
            yield from host._fail(context, "project_init_scope_violation")
            return
    context.built_change_set = built
    context.machine.transition(RunState.CHANGESET_PROPOSED)
    yield host._event(
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
        workspace_identity=host._policy_binding(context.command.workspace_root)[0],
        policy_hash=host.policy_engine.policy_hash,
        fact_hash=built.facts_digest(),
        **host._security_approval_kwargs(context),
    )
    yield host._stable_event(
        context,
        "approval.required",
        host._approval_payload(request),
        RecoveryStage.AWAITING_CHANGESET_APPROVAL,
    )


def expire_approval(
    host: ApprovalFlowHost,
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
    yield host._stable_event(
        context,
        "approval.expired",
        payload,
        RecoveryStage.AWAITING_CHANGESET_APPROVAL,
    )


def resolve_approval(host: ApprovalFlowHost, command: ResolveApproval) -> Iterator[EventEnvelope]:
    context = host.runs.get(command.run_id)
    if context is None:
        yield from host._expire_approval(None, command, "cross_run")
        return
    request = context.approval_gate.pending_approval
    if request is None:
        return
    try:
        decision = context.approval_gate.resolve(command)
    except ApprovalMismatch as exc:
        yield from host._expire_approval(
            context,
            command,
            exc.reason,
            approval_id=request.approval_id,
        )
        return
    identity, current_hash = host._policy_binding(context.command.workspace_root)
    if request.policy_hash is not None and request.policy_hash != current_hash:
        yield host._stable_event(
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
        yield host._stable_event(
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
        yield host._stable_event(
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
            yield from host._expire_approval(
                context,
                command,
                "missing_fact_binding",
                approval_id=request.approval_id,
            )
            return
        built = context.built_change_set
        expired = built is None or built.facts_digest() != request.fact_hash
        if not expired and built is not None:
            paths = (
                PermissionPaths(host.access_session)
                if host.access_session is not None
                else WorkspacePaths(context.command.workspace_root)
            )
            try:
                for fact in built.path_facts.values():
                    paths.revalidate(fact)
            except WorkspaceBoundaryError:
                expired = True
        if expired:
            yield from host._expire_approval(
                context,
                command,
                "fact_changed",
                approval_id=request.approval_id,
            )
            return
    if request.kind == ApprovalKind.COMMAND.value:
        pending = context.pending_command
        if pending is None or not host._verification_binding_matches(
            context, pending, context.verification_index
        ):
            yield from host._expire_approval(
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
            yield from host._expire_approval(
                context,
                command,
                "tool_binding_changed",
                approval_id=request.approval_id,
            )
            return
    yield host._event(
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
            yield host._stable_event(
                context,
                "verification.completed",
                host._verification_event_payload(
                    index,
                    pending or VerificationCommand(argv=()),
                    extra={"status": "rejected"},
                ),
                RecoveryStage.VERIFYING,
            )
        elif context.pending_command is not None:
            pending = context.pending_command
            index = context.verification_index
            span = start_verification_span(context, index, pending)
            try:
                result = host._verification_runner(context).run(pending)
            except Exception:
                verification_span_error(context, span)
                raise
            finish_verification_span(context, span, result)
            context.verification_failed = context.verification_failed or result.status != "passed"
            context.pending_command = None
            context.verification_index += 1
            completed_payload = host._verification_event_payload(index, pending, result)
            completed_payload["span_id"] = span.span_id
            yield host._stable_event(
                context,
                "verification.completed",
                completed_payload,
                RecoveryStage.VERIFYING,
            )
        yield from host._verify(context)
        return
    if request.kind == ApprovalKind.RECOVERY.value:
        if decision == "reject":
            context.pending_recovery_plan = None
            yield host._stable_event(
                context,
                "recovery.detected",
                host._report_payload(host.coordinator.prepare_resume(context.run_id)),
                RecoveryStage.CHECKPOINT_READY,
            )
            return
        yield from host._apply_recovery_plan(context, request)
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
        context.tool_approval_outcomes[call.call_id] = {
            "approval_id": request.approval_id,
            "action_id": pending_tool.action.action_id,
            "decision": decision,
            "source": "core_approval_gate",
        }
        if decision == "reject":
            span = context.trace_recorder.start_span(
                "tool",
                call.name[:128],
                attributes={"tool_name": call.name[:128], "tool_call_id": call.call_id[:128]},
            )
            context.active_tool_span_id = span.span_id
            yield from host._emit_tool_result(
                context,
                call,
                ToolResult(ok=False, error_code="approval_rejected"),
            )
            context.active_tool_span_id = None
            context.trace_recorder.finish_span(
                span, "rejected", attributes={"error_code": "approval_rejected"}
            )
            context.machine.transition(RunState.DISCOVERING)
            yield host._stable_event(
                context,
                "tool.action_resolved",
                {"action_id": pending_tool.action.action_id, "status": "rejected"},
                RecoveryStage.STARTED,
            )
            for output in host._drive(context):
                if isinstance(output, EventEnvelope):
                    yield output
            return
        executor = host._tool_executor(context)
        implementation = executor.registry.implementation(pending_tool.action.tool_name)
        if implementation is None:
            yield from host._expire_approval(
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
            (
                mutation,
                process_plan,
                git_commit_plan,
                git_branch_plan,
                git_init_plan,
            ) = executor._plan_action(
                implementation,
                context.run_id,
                parsed,
                action_id=pending_tool.action.action_id,
            )
            current_facts = executor._risk_facts(implementation, parsed)
            if mutation is not None:
                current_facts = current_facts.model_copy(
                    update={"target_facts_hash": mutation.plan.target_facts_hash}
                )
        except Exception:
            yield from host._expire_approval(
                context,
                command,
                "tool_fact_changed",
                approval_id=request.approval_id,
            )
            return
        if executor.policy_engine.policy_hash != request.policy_hash:
            yield from host._expire_approval(
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
            mutation=mutation,
            process_plan=process_plan,
            git_commit_plan=git_commit_plan,
            git_branch_plan=git_branch_plan,
            git_init_plan=git_init_plan,
        )
        if executor.facts_hash(current_facts) != pending_tool.target_facts_hash:
            yield from host._expire_approval(
                context,
                command,
                "tool_fact_changed",
                approval_id=request.approval_id,
            )
            return
        span = context.trace_recorder.start_span(
            "tool",
            call.name[:128],
            attributes={
                "tool_name": call.name[:128],
                "tool_call_id": call.call_id[:128],
                "input_content_hash": pending_tool.action.input_hash,
                "approved": True,
            },
        )
        context.active_tool_span_id = span.span_id
        try:
            tool_result, tool_events = host._execute_prepared_tool(
                context, call, executor, prepared, approved=True
            )
        except Exception:
            context.trace_recorder.finish_span(
                span, "error", attributes={"error_code": "tool_execution_error"}
            )
            raise
        finally:
            context.active_tool_span_id = None
        context.trace_recorder.finish_span(
            span,
            "ok" if tool_result.ok else "error",
            attributes={
                "error_code": tool_result.error_code,
                "truncated": tool_result.truncated,
            },
        )
        yield from tool_events
        context.machine.transition(RunState.DISCOVERING)
        yield host._stable_event(
            context,
            "tool.action_resolved",
            {
                "action_id": pending_tool.action.action_id,
                "status": "completed" if tool_result.ok else "failed",
                "error_code": tool_result.error_code,
            },
            RecoveryStage.STARTED,
        )
        for output in host._drive(context):
            if isinstance(output, EventEnvelope):
                yield output
        return
    if decision == "reject":
        context.machine.transition(RunState.CANCELLED)
        yield host._stable_event(
            context,
            "run.cancelled",
            {"reason": "approval_rejected"},
            RecoveryStage.TERMINAL,
        )
        return
    built = context.built_change_set
    if built is None:
        yield from host._fail(context, "missing_changeset")
        return
    paths = (
        PermissionPaths(host.access_session)
        if host.access_session is not None
        else WorkspacePaths(context.command.workspace_root)
    )
    store = CheckpointStore(host.state_dir, paths)
    applier = ChangeApplier(paths, store, writer=host.file_writer)
    try:
        context.machine.transition(RunState.CHECKPOINTING)
        manifest = store.create(built.change_set)
    except Exception as exc:
        yield from host._fail(context, f"checkpoint_failed:{exc}")
        return
    context.checkpoint_manifest = manifest
    yield host._stable_event(
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
        yield host._event(
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
        yield from host._fail(context, apply_result.error_code or apply_result.status.value)
        return
    context.workspace_write_started = True
    yield host._stable_event(
        context,
        "changeset.applied",
        {"status": apply_result.status.value},
        RecoveryStage.VERIFYING,
    )
    context.machine.transition(RunState.VERIFYING)
    yield from host._verify(context)


class ApprovalFlow:
    """Stable façade for proposal and approval lifecycle operations."""

    approval_payload = staticmethod(approval_payload)
    propose = staticmethod(propose)
    expire = staticmethod(expire_approval)
    resolve = staticmethod(resolve_approval)
