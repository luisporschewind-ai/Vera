"""Structured session status models shared by Core and CLI."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ConversationStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    message_count: int = Field(ge=0)
    context_bytes: int = Field(ge=0)
    max_bytes: int = Field(ge=1)
    warning: bool
    compaction_count: int = Field(ge=0)


class PermissionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_mode: str
    changeset_approval: str
    command_policy: str
    user_allowed_prefixes: tuple[tuple[str, ...], ...]
    execution_boundary: str
    os_sandbox: bool


class GitStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    branch: str | None
    dirty: bool | None


class SessionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    model_profile: str
    model_name: str
    workspace: Path
    git: GitStatus
    context: ConversationStats
    permissions: PermissionStatus
