"""Structured session status models shared by Core and CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConversationStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    message_count: int = Field(ge=0)
    context_bytes: int = Field(ge=0)
    max_bytes: int = Field(ge=1)
    warning: bool
    compaction_count: int = Field(ge=0)
    source: Literal["new", "continued", "resumed"] = "new"
    title: str = "新会话"
    persistent_state: Literal["saved", "unsaved"] = "saved"
    last_saved_sequence: int | None = Field(default=None, ge=1)
    last_error_code: str | None = None


class PermissionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_mode: str
    changeset_approval: str
    command_policy: str
    user_allowed_prefixes: tuple[tuple[str, ...], ...]
    execution_boundary: str
    os_sandbox: bool
    policy_version: int = 1
    policy_hash_prefix: str = ""
    hard_denies: tuple[str, ...] = ()
    policy_mode: Literal["review", "balanced", "autonomous"] = "balanced"
    trusted: bool = False
    approval_scopes: tuple[str, ...] = ("once", "run", "workspace")


class GitStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    branch: str | None
    dirty: bool | None


class ReasoningStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["explicit", "provider_default", "unavailable"]
    effort: str | None = None

    @model_validator(mode="after")
    def _effort_matches_mode(self) -> ReasoningStatus:
        if self.mode == "explicit":
            if not self.effort:
                raise ValueError("explicit reasoning requires effort")
            return self
        if self.effort is not None:
            raise ValueError("non-explicit reasoning must omit effort")
        return self

    def display_label(self) -> str:
        if self.mode == "explicit" and self.effort:
            return self.effort
        if self.mode == "provider_default":
            return "模型默认"
        return "不可用"


class SessionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    model_profile: str
    model_name: str
    workspace: Path
    git: GitStatus
    context: ConversationStats
    permissions: PermissionStatus
    reasoning: ReasoningStatus = Field(default_factory=lambda: ReasoningStatus(mode="unavailable"))
