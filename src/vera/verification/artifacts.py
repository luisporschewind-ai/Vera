"""Compatibility facade for verification artifact planning."""

from __future__ import annotations

import shutil  # noqa: F401

from vera.verification.artifact_paths import (
    VerificationArtifactError,
    artifact_root,
    default_verification_prefix,
    installation_prefix,
    with_workspace_runtime_path,
    workspace_bin_dirs,
    workspace_tool_path,
)
from vera.verification.artifact_planner import VerificationArtifactPlanner
from vera.verification.artifact_root import (
    CleanupResult,
    CleanupStatus,
    VerificationArtifactRoot,
    environment_for_plan,
)

__all__ = [
    "CleanupResult",
    "CleanupStatus",
    "VerificationArtifactError",
    "VerificationArtifactPlanner",
    "VerificationArtifactRoot",
    "artifact_root",
    "default_verification_prefix",
    "environment_for_plan",
    "installation_prefix",
    "with_workspace_runtime_path",
    "workspace_bin_dirs",
    "workspace_tool_path",
]
