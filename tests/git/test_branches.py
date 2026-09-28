from __future__ import annotations

from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.git.branches import GitBrancher, GitBranchError, GitBranchPlanBuilder
from vera.git.service import GitService


def test_branch_create_is_exact_and_receipted(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    service = GitService(repository, environment=env)
    plan = GitBranchPlanBuilder(service).build(
        run_id="run-1",
        action_id="action-1",
        operation="create",
        branch_name="feature/native-git",
        policy_hash="policy-1",
    )

    result = GitBrancher(service, state_dir=tmp_path / "state").execute(plan)

    assert result.branch_name == "feature/native-git"
    assert run_git(repository, "branch", "--show-current", env=env).strip() == result.old_branch
    assert run_git(repository, "show-ref", "--verify", "refs/heads/feature/native-git", env=env)


def test_branch_switch_requires_clean_facts_and_verifies_head(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "branch", "feature/native-git", env=env)
    service = GitService(repository, environment=env)
    plan = GitBranchPlanBuilder(service).build(
        run_id="run-1",
        action_id="action-1",
        operation="switch",
        branch_name="feature/native-git",
        policy_hash="policy-1",
    )

    result = GitBrancher(service, state_dir=tmp_path / "state").execute(plan)

    assert result.new_branch == "feature/native-git"
    assert run_git(repository, "branch", "--show-current", env=env).strip() == "feature/native-git"


def test_branch_plan_rejects_dirty_or_invalid_targets(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    service = GitService(repository, environment=env)
    (repository / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(GitBranchError, match="git_branch_dirty"):
        GitBranchPlanBuilder(service).build(
            run_id="run-1",
            action_id="action-1",
            operation="create",
            branch_name="feature/native-git",
            policy_hash="policy-1",
        )

    (repository / "dirty.txt").unlink()
    with pytest.raises(GitBranchError, match="git_invalid_branch_name"):
        GitBranchPlanBuilder(service).build(
            run_id="run-1",
            action_id="action-1",
            operation="create",
            branch_name="-bad",
            policy_hash="policy-1",
        )
