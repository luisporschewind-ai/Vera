"""Structured process-action contracts used by the Core bash tool."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator

from vera.contracts import ContractModel
from vera.policy.models import RiskLevel


class BashInput(ContractModel):
    """A process invocation; argv is never interpreted as shell source."""

    argv: tuple[str, ...] = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=1800)

    @field_validator("argv")
    @classmethod
    def argv_is_safe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not isinstance(item, str) or "\x00" in item for item in value):
            raise ValueError("argv must be non-empty and contain no NUL bytes")
        return value

    @field_validator("cwd")
    @classmethod
    def cwd_is_relative(cls, value: str) -> str:
        if not value or not value.strip() or "\x00" in value:
            raise ValueError("cwd must be a non-empty path without NUL bytes")
        normalized = value.replace("\\", "/")
        candidate = PurePosixPath(normalized)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("cwd must stay inside the workspace")
        return value


class CommandActionPlan(ContractModel):
    """Immutable facts bound before a process can be executed."""

    schema_version: Literal[1] = 1
    action_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    argv: tuple[str, ...] = Field(min_length=1)
    cwd: str = Field(min_length=1)
    executable: str = Field(min_length=1)
    risk_level: RiskLevel
    writes_workspace: bool = False
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
