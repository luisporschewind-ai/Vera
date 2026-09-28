from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.recovery.probe import workspace_identity
from vera.tools.executor import ToolExecutor
from vera.tools.git import GitCommitTool
from vera.tools.registry import ToolRegistry


@pytest.fixture
def commit_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Vera Test",
            "GIT_AUTHOR_EMAIL": "vera-test@example.invalid",
            "GIT_COMMITTER_NAME": "Vera Test",
            "GIT_COMMITTER_EMAIL": "vera-test@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init", "--quiet", env=env)
    (repository / "README.md").write_text("initial\n", encoding="utf-8")
    run_git(repository, "add", "--", "README.md", env=env)
    run_git(repository, "commit", "--quiet", "-m", "initial", env=env)
    return repository, env


def test_git_commit_tool_runs_through_tool_executor_and_preserves_other_staged_content(
    commit_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = commit_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
    (repository / "user.txt").write_text("staged by user\n", encoding="utf-8")
    run_git(repository, "add", "--", "user.txt", env=env)
    identity = workspace_identity(repository, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    tool = GitCommitTool(repository, environment=env)
    registry = ToolRegistry()
    registry.register(tool)
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=tmp_path / "state",
    )

    prepared = executor.prepare(
        run_id="run-1",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-1"],
            "verification_status": "passed",
        },
    )
    assert prepared.policy_decision.decision.value == "allow"

    result = executor.execute_allowed(prepared)

    assert result.ok is True
    assert result.content["committed_paths"] == ["app.py"]
    assert run_git(repository, "diff", "--cached", "--name-only", env=env).strip() == "user.txt"


def test_untrusted_workspace_denies_commit_when_commit_hook_is_present(
    commit_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = commit_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o700)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
    identity = workspace_identity(repository, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
    )
    tool = GitCommitTool(repository, environment=env)
    registry = ToolRegistry()
    registry.register(tool)
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=tmp_path / "state",
    )

    prepared = executor.prepare(
        run_id="run-1",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-1"],
            "verification_status": "passed",
        },
    )

    assert prepared.policy_decision.decision.value == "deny"
    assert prepared.policy_decision.reason_code == "risk_forbidden"


def test_trusted_workspace_requires_approval_for_a_commit_hook(
    commit_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = commit_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o700)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
    identity = workspace_identity(repository, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    registry = ToolRegistry()
    registry.register(GitCommitTool(repository, environment=env))
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=tmp_path / "state",
    )

    prepared = executor.prepare(
        run_id="run-1",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-1"],
            "verification_status": "passed",
        },
    )

    assert prepared.policy_decision.decision.value == "approval_required"
    assert prepared.policy_decision.reason_code == "high_risk_approval_required"
