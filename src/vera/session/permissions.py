"""Effective permission snapshots derived from the injected PolicyEngine."""

from __future__ import annotations

from typing import Literal

from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyMode
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.process.supervisor import ProcessSupervisor
from vera.sandbox.backend import SrtBackend
from vera.sandbox.settings import UnavailableBackend
from vera.sandbox.supervision import SandboxedSupervisor
from vera.session.models import PermissionStatus
from vera.tools.command_policy import CommandPolicy


def permission_status(
    policy: CommandPolicy,
    *,
    policy_engine: PolicyEngine | None = None,
    workspace_permissions: WorkspacePermissionSnapshot | None = None,
    process_supervisor: ProcessSupervisor | None = None,
) -> PermissionStatus:
    engine = policy_engine or policy.engine
    snapshot = engine.snapshot
    raw_mode = getattr(snapshot, "policy_mode", PolicyMode.BALANCED)
    mode: Literal["review", "balanced", "autonomous"] = (
        raw_mode.value if isinstance(raw_mode, PolicyMode) else "balanced"
    )
    sandbox_state: Literal["none", "setup_required", "configured", "required"] = "none"
    sandboxed = isinstance(process_supervisor, SandboxedSupervisor)
    if isinstance(process_supervisor, SandboxedSupervisor):
        if isinstance(process_supervisor.backend, UnavailableBackend):
            sandbox_state = "setup_required"
        elif isinstance(process_supervisor.backend, SrtBackend):
            sandbox_state = "configured"
        else:
            sandbox_state = "required"
    return PermissionStatus(
        approval_mode="manual",
        changeset_approval="required",
        command_policy="allow/deny/approval-required",
        user_allowed_prefixes=tuple(policy.user_allowed_prefixes),
        execution_boundary=(
            "trusted Core; sandbox required for commands" if sandboxed else "current user"
        ),
        # Describes the configured execution route, not a successful OS probe.
        os_sandbox=sandbox_state == "configured",
        sandbox_state=sandbox_state,
        network="deny" if sandboxed else None,
        policy_version=engine.snapshot.builtin_policy_version,
        policy_hash_prefix=engine.policy_hash[:12],
        hard_denies=("shell", "sudo", "rm", "sensitive_paths"),
        policy_mode=mode,
        trusted=bool(workspace_permissions.trusted) if workspace_permissions else False,
    )
