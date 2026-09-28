"""Verification planning and execution flow."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryStage
from vera.contracts.trace import TraceSpanStatus
from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.runtime.approval import ApprovalKind
from vera.runtime.context import RunContext
from vera.runtime.flow_protocols import VerificationFlowHost
from vera.runtime.security import collected_risk_labels, worst_disposition
from vera.runtime.state import RunState
from vera.tools.command_policy import CommandDecisionKind
from vera.trace.recorder import SpanHandle
from vera.verification.artifacts import VerificationArtifactPlanner, artifact_root
from vera.verification.runner import VerificationRunner


def planner(host: VerificationFlowHost) -> VerificationArtifactPlanner:
    return VerificationArtifactPlanner(prefix=host.artifact_prefix)


def verification_runner(host: VerificationFlowHost, context: RunContext) -> VerificationRunner:
    return VerificationRunner(
        context.command.workspace_root,
        artifact_prefix=host.artifact_prefix,
        supervisor=host.process_supervisor,
    )


def plan_verification(
    host: VerificationFlowHost,
    context: RunContext,
    commands: Sequence[VerificationCommand],
) -> tuple[VerificationCommand, ...]:
    planner = host._planner()
    planned: list[VerificationCommand] = []
    for index, command in enumerate(commands):
        planned.append(
            planner.plan(
                command,
                workspace_root=context.command.workspace_root,
                installation_id=host.installation_id,
                run_id=context.run_id,
                index=index,
            )
        )
    return tuple(planned)


def expected_artifact_root(host: VerificationFlowHost, context: RunContext, index: int) -> Path:
    return artifact_root(
        workspace_root=context.command.workspace_root,
        installation_id=host.installation_id,
        run_id=context.run_id,
        index=index,
        prefix=host.artifact_prefix,
    )


def verification_binding_matches(
    host: VerificationFlowHost, context: RunContext, command: VerificationCommand, index: int
) -> bool:
    plan = command.artifact_plan
    if plan is None or plan.root is None:
        return False
    return plan.root == str(host._expected_artifact_root(context, index))


def verification_event_payload(
    host: VerificationFlowHost,
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


def start_verification_span(
    context: RunContext, index: int, command: VerificationCommand
) -> SpanHandle:
    profile = command.artifact_plan.profile if command.artifact_plan is not None else None
    return context.trace_recorder.start_span(
        "verification",
        "verification command",
        attributes={"index": index, "artifact_profile": profile},
    )


def finish_verification_span(
    context: RunContext, span: SpanHandle, result: VerificationResult
) -> None:
    status: TraceSpanStatus
    if result.status == "passed":
        status = "ok"
    elif result.status == "cancelled":
        status = "cancelled"
    elif result.status == "rejected":
        status = "rejected"
    else:
        status = "error"
    attributes: dict[str, Any] = {
        "status": result.status,
        "reported_duration_ms": result.duration_seconds * 1000,
        "exit_code": result.exit_code,
        "stdout_byte_count": len(result.stdout.encode("utf-8")),
        "stderr_byte_count": len(result.stderr.encode("utf-8")),
        "stdout_truncated": result.stdout_truncated,
        "stderr_truncated": result.stderr_truncated,
        "artifact_cleanup_status": result.artifact_cleanup_status,
        "workspace_mutation_count": len(result.workspace_mutations),
    }
    if result.reason_code is not None:
        attributes["reason_code"] = result.reason_code[:128]
    context.trace_recorder.finish_span(
        span, status, attributes=attributes, duration_ms=result.duration_seconds * 1000
    )


def verification_span_error(context: RunContext, span: SpanHandle) -> None:
    context.trace_recorder.finish_span(
        span, "error", attributes={"error_code": "verification_runner_error"}
    )


def verify(host: VerificationFlowHost, context: RunContext) -> Iterator[EventEnvelope]:
    built = context.built_change_set
    if built is None:
        yield from host._fail(context, "missing_changeset")
        return
    runner = host._verification_runner(context)
    policy = host.command_policy
    while context.verification_index < len(built.change_set.verification):
        index = context.verification_index
        command = built.change_set.verification[index]
        if not host._verification_binding_matches(context, command, index):
            context.verification_failed = True
            context.verification_index += 1
            context.pending_command = None
            yield host._stable_event(
                context,
                "verification.completed",
                host._verification_event_payload(
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
            yield host._stable_event(
                context,
                "verification.completed",
                host._verification_event_payload(
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
                workspace_identity=host._policy_binding(context.command.workspace_root)[0],
                policy_hash=host.policy_engine.policy_hash,
                **host._security_approval_kwargs(context),
            )
            payload = host._approval_payload(request, context)
            yield host._stable_event(
                context,
                "approval.required",
                payload,
                RecoveryStage.AWAITING_VERIFICATION_APPROVAL,
            )
            return
        span = start_verification_span(context, index, command)
        started_payload = host._verification_event_payload(index, command)
        started_payload["span_id"] = span.span_id
        yield host._stable_event(
            context,
            "verification.started",
            started_payload,
            RecoveryStage.VERIFYING,
        )
        try:
            result = runner.run(command)
        except Exception:
            verification_span_error(context, span)
            raise
        finish_verification_span(context, span, result)
        context.verification_failed = context.verification_failed or result.status != "passed"
        context.verification_index += 1
        completed_payload = host._verification_event_payload(index, command, result)
        completed_payload["span_id"] = span.span_id
        yield host._stable_event(
            context,
            "verification.completed",
            completed_payload,
            RecoveryStage.VERIFYING,
        )
    terminal = RunState.VERIFICATION_FAILED if context.verification_failed else RunState.COMPLETED
    context.machine.transition(terminal)
    yield host._stable_event(
        context,
        "run.completed",
        {"state": context.machine.state.value},
        RecoveryStage.TERMINAL,
    )


class VerificationFlow:
    """Stable façade for verification planning and execution."""

    planner = staticmethod(planner)
    verification_runner = staticmethod(verification_runner)
    plan = staticmethod(plan_verification)
    expected_artifact_root = staticmethod(expected_artifact_root)
    binding_matches = staticmethod(verification_binding_matches)
    event_payload = staticmethod(verification_event_payload)
    verify = staticmethod(verify)
