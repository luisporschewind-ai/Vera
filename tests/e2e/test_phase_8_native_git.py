from __future__ import annotations

import os
from pathlib import Path

from tests.git.conftest import run_git
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.recovery.probe import workspace_identity
from vera.tools.executor import ToolExecutor
from vera.tools.git import (
    GitBranchCreateTool,
    GitBranchSwitchTool,
    GitCommitTool,
    GitDiffTool,
    GitLogTool,
    GitShowTool,
    GitStatusTool,
)
from vera.tools.registry import ToolRegistry


def _repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Vera Phase8",
            "GIT_AUTHOR_EMAIL": "phase8@example.invalid",
            "GIT_COMMITTER_NAME": "Vera Phase8",
            "GIT_COMMITTER_EMAIL": "phase8@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", env=env)
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    run_git(repo, "add", "--", "README.md", env=env)
    run_git(repo, "commit", "-qm", "fixture", env=env)
    return repo, env


def _executor(repo: Path, state: Path) -> ToolExecutor:
    identity = workspace_identity(repo, "phase8")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    registry = ToolRegistry()
    for tool in (
        GitStatusTool(repo),
        GitDiffTool(repo),
        GitLogTool(repo),
        GitShowTool(repo),
        GitCommitTool(repo),
        GitBranchCreateTool(repo),
        GitBranchSwitchTool(repo),
    ):
        registry.register(tool)
    return ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=state,
    )


def test_phase8_native_git_read_and_exact_commit_branch_matrix(tmp_path: Path) -> None:
    repo, env = _repo(tmp_path)
    state = tmp_path / "state"
    executor = _executor(repo, state)

    for name, arguments in (
        ("git_status", {}),
        ("git_diff", {"scope": "working"}),
        ("git_log", {}),
        ("git_show", {"ref": "HEAD"}),
    ):
        prepared = executor.prepare(run_id="run-git", name=name, arguments=arguments)
        assert prepared.policy_decision.decision.value == "allow"
        assert executor.execute_allowed(prepared).ok is True

    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    commit = executor.prepare(
        run_id="run-git",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-git"],
            "verification_status": "passed",
        },
    )
    assert executor.execute_allowed(commit).ok is True
    assert run_git(repo, "show", "-s", "--format=%s", env=env).strip() == "Add app"
    assert run_git(repo, "status", "--short", env=env).strip() == ""

    create = executor.prepare(
        run_id="run-git",
        name="git_branch_create",
        arguments={"branch_name": "feature/phase8"},
    )
    assert create.policy_decision.decision.value == "approval_required"
    assert executor.execute_allowed(create, approved=True).ok is True
    switch = executor.prepare(
        run_id="run-git",
        name="git_branch_switch",
        arguments={"branch_name": "feature/phase8"},
    )
    assert executor.execute_allowed(switch, approved=True).ok is True
    assert run_git(repo, "branch", "--show-current", env=env).strip() == "feature/phase8"


def test_phase8_untrusted_hook_is_denied_before_commit(tmp_path: Path) -> None:
    repo, _env = _repo(tmp_path)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o700)
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    identity = workspace_identity(repo, "phase8")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
    )
    registry = ToolRegistry()
    registry.register(GitCommitTool(repo))
    executor = ToolExecutor(registry, PolicyEngine(snapshot), permissions, goal_authorized=True)

    prepared = executor.prepare(
        run_id="run-git",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-git"],
            "verification_status": "passed",
        },
    )
    assert prepared.policy_decision.decision.value == "deny"
