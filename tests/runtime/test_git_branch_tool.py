from __future__ import annotations

from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.recovery.probe import workspace_identity
from vera.tools.executor import ToolExecutor
from vera.tools.git import GitBranchCreateTool
from vera.tools.registry import ToolRegistry


@pytest.fixture
def branch_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    env = {
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
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init", "--quiet", env=env)
    (repository / "README.md").write_text("initial\n", encoding="utf-8")
    run_git(repository, "add", "--", "README.md", env=env)
    run_git(repository, "commit", "--quiet", "-m", "initial", env=env)
    return repository, env


def test_branch_create_uses_tool_executor_and_requires_approval(
    branch_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = branch_repo
    identity = workspace_identity(repository, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    registry = ToolRegistry()
    registry.register(GitBranchCreateTool(repository, environment=env))
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
        state_dir=tmp_path / "state",
    )

    prepared = executor.prepare(
        run_id="run-1",
        name="git_branch_create",
        arguments={"branch_name": "feature/tool"},
    )
    assert prepared.policy_decision.decision.value == "approval_required"

    result = executor.execute_allowed(prepared, approved=True)

    assert result.ok is True
    assert run_git(repository, "show-ref", "--verify", "refs/heads/feature/tool", env=env)
