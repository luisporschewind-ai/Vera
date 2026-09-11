"""Workspace path policy depth-defense tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecisionKind
from vera.policy.snapshot import EffectivePolicySnapshot
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


def test_user_rule_cannot_allow_sensitive_file(tmp_path: Path) -> None:
    engine = PolicyEngine(
        EffectivePolicySnapshot(
            workspace_identity="ws",
            user_allowed_command_prefixes=(),
        )
    )
    decision = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.PATH_READ,
            workspace_identity="ws",
            resource=str(tmp_path / ".env"),
        )
    )
    assert decision.decision is PolicyDecisionKind.DENY
    assert decision.reason_code == "sensitive_path_forbidden"


def test_policy_allow_still_cannot_escape_workspace(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path)
    with pytest.raises(WorkspaceBoundaryError):
        paths.resolve_read("../secret.txt")
