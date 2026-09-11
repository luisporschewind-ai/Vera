"""Effective permission snapshots derived from the injected CommandPolicy."""

from __future__ import annotations

from vera.session.models import PermissionStatus
from vera.tools.command_policy import CommandPolicy


def permission_status(policy: CommandPolicy) -> PermissionStatus:
    return PermissionStatus(
        approval_mode="manual",
        changeset_approval="required",
        command_policy="allow/deny/approval-required",
        user_allowed_prefixes=tuple(policy.user_allowed_prefixes),
        execution_boundary="current user",
        os_sandbox=False,
    )
