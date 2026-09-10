"""Verification command and result contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from vera.contracts import ContractModel


class VerificationCommand(ContractModel):
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1)
    required: bool = True


class VerificationResult(ContractModel):
    schema_version: Literal[1] = 1
    argv: tuple[str, ...]
    cwd: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    status: Literal["passed", "failed", "timed_out", "rejected", "error"]
