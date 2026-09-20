"""Effective permission snapshots derived from the injected PolicyEngine."""

from __future__ import annotations

from typing import Literal

from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyMode
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.session.models import PermissionStatus
from vera.tools.command_policy import CommandPolicy


def permission_status(
    policy: CommandPolicy,
    *,
    policy_engine: PolicyEngine | None = None,
    workspace_permissions: WorkspacePermissionSnapshot | None = None,
) -> PermissionStatus:
    engine = policy_engine or policy.engine
    snapshot = engine.snapshot
    raw_mode = getattr(snapshot, "policy_mode", PolicyMode.BALANCED)
    mode: Literal["review", "balanced", "autonomous"] = (
        raw_mode.value if isinstance(raw_mode, PolicyMode) else "balanced"
    )
    return PermissionStatus(
        approval_mode="manual",
        changeset_approval="required",
        command_policy="allow/deny/approval-required",
        user_allowed_prefixes=tuple(policy.user_allowed_prefixes),
        execution_boundary="current user",
        os_sandbox=False,
        policy_version=engine.snapshot.builtin_policy_version,
        policy_hash_prefix=engine.policy_hash[:12],
        hard_denies=("shell", "sudo", "rm", "sensitive_paths"),
        policy_mode=mode,
        trusted=bool(workspace_permissions.trusted) if workspace_permissions else False,
    )
