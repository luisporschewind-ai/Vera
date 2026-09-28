from __future__ import annotations

import subprocess
from pathlib import Path

from vera.contracts.commands import StartRun
from vera.contracts.tool_actions import ToolEffect
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import PermissionGrant, WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.runtime.engine import VeraRuntime
from vera.tools.executor import ToolExecutor
from vera.tools.git import GitRepositoryInitTool
from vera.tools.registry import ToolRegistry


def _executor(workspace: Path, *, trusted: bool = True) -> ToolExecutor:
    identity = "git-init-test-workspace"
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=trusted,
    )
    registry = ToolRegistry()
    registry.register(GitRepositoryInitTool(workspace))
    return ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=workspace.parent / "vera-state",
    )


def test_initialization_always_requires_explicit_approval_in_trusted_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()

    prepared = _executor(workspace).prepare(
        run_id="run-1", name="git_repository_init", arguments={}
    )

    assert prepared.policy_decision.decision.value == "approval_required"
    assert prepared.policy_decision.reason_code == "high_risk_approval_required"


def test_workspace_grant_cannot_bypass_initialization_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    identity = "git-init-test-workspace"
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
        grants=(
            PermissionGrant(
                grant_id="broad-init-grant",
                scope="workspace",
                tool_name="git_repository_init",
                effects=(ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE),
                argument_constraints={"initial_branch": None},
            ),
        ),
    )
    registry = ToolRegistry()
    registry.register(GitRepositoryInitTool(workspace))
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=workspace.parent / "vera-state",
    )

    prepared = executor.prepare(run_id="run-1", name="git_repository_init", arguments={})

    assert prepared.policy_decision.decision.value == "approval_required"


def test_unapproved_initialization_does_not_create_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    executor = _executor(workspace)
    prepared = executor.prepare(run_id="run-1", name="git_repository_init", arguments={})

    result = executor.execute_allowed(prepared)

    assert result.ok is False
    assert result.error_code == "approval_required"
    assert not (workspace / ".git").exists()


def test_approved_initialization_fails_closed_without_sandbox_backend(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    executor = _executor(workspace)
    prepared = executor.prepare(run_id="run-1", name="git_repository_init", arguments={})

    result = executor.execute_allowed(prepared, approved=True)

    assert result.ok is False
    assert result.error_code == "git_init_backend_unsupported"
    assert not (workspace / ".git").exists()


def test_existing_repository_is_returned_without_initialization_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
    executor = _executor(workspace)

    prepared = executor.prepare(run_id="run-1", name="git_repository_init", arguments={})
    result = executor.execute_allowed(prepared)

    assert prepared.policy_decision.decision.value == "allow"
    assert result.ok is True
    assert result.content["status"] == "already_initialized"


def test_approval_preview_names_exact_workspace_and_initial_branch(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register(GitRepositoryInitTool(workspace))
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="init-1",
                            name="git_repository_init",
                            arguments={"initial_branch": "trunk"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="等待初始化审批。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
    )

    events = list(
        runtime.handle(
            StartRun(goal="初始化本地仓库", workspace_root=workspace, model_profile="fake")
        )
    )

    approval = next(event for event in events if event.type == "approval.required")
    assert approval.payload["workspace"] == str(workspace)
    assert approval.payload["target"] == str(workspace / ".git")
    assert "初始分支 trunk" in approval.payload["description"]
    assert "不创建提交、远程、身份或 Hook" in approval.payload["description"]
    assert not (workspace / ".git").exists()
