"""Unified policy decision models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyDecisionKind(StrEnum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


class PolicyActionKind(StrEnum):
    PATH_READ = "path_read"
    PATH_WRITE = "path_write"
    TOOL_EXECUTE = "tool_execute"
    COMMAND_EXECUTE = "command_execute"
    CHANGESET_APPLY = "changeset_apply"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    RECOVERY_RESUME = "recovery_resume"
    STATE_MIGRATE = "state_migrate"


class PolicyAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: PolicyActionKind
    workspace_identity: str
    resource: str
    argv: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: PolicyDecisionKind
    reason_code: str
    reason: str
    matched_rule: str
    policy_hash: str
