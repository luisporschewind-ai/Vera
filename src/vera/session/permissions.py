"""Effective permission snapshots derived from the injected PolicyEngine."""

from __future__ import annotations

from vera.policy.engine import PolicyEngine
from vera.session.models import PermissionStatus
from vera.tools.command_policy import CommandPolicy


def permission_status(
    policy: CommandPolicy, *, policy_engine: PolicyEngine | None = None
) -> PermissionStatus:
    engine = policy_engine or policy.engine
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
    )
