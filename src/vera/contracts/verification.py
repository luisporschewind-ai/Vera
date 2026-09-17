"""Verification command and result contracts."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from vera.contracts import ContractModel

ARTIFACT_PROFILES = (
    "xcode",
    "swiftpm",
    "pytest",
    "mypy",
    "ruff_no_cache",
    "git_readonly",
    "tsc_no_emit",
)

ArtifactProfile = Literal[
    "xcode",
    "swiftpm",
    "pytest",
    "mypy",
    "ruff_no_cache",
    "git_readonly",
    "tsc_no_emit",
]

ArtifactCleanupStatus = Literal["cleaned", "skipped", "failed"]


class VerificationArtifactPlan(ContractModel):
    schema_version: Literal[1] = 1
    profile: ArtifactProfile
    root: str | None = None
    cleanup: Literal["always"] = "always"

    @field_validator("root")
    @classmethod
    def root_must_be_absolute(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not Path(value).is_absolute():
            raise ValueError("artifact root must be absolute")
        return value


class VerificationCommand(ContractModel):
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1)
    required: bool = True
    artifact_plan: VerificationArtifactPlan | None = None


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
    status: Literal[
        "passed",
        "failed",
        "timed_out",
        "cancelled",
        "rejected",
        "error",
        "workspace_polluted",
    ]
    artifact_profile: ArtifactProfile | None = None
    artifact_root: str | None = None
    artifact_cleanup_status: ArtifactCleanupStatus | None = None
    workspace_mutations: tuple[str, ...] = ()
    reason_code: str | None = None
