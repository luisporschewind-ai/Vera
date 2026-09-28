from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from vera.git.initialize import (
    GitRepositoryInitError,
    GitRepositoryInitService,
    GitRepositoryInitStatus,
)
from vera.process.supervisor import ProcessResult


class _TestOnlyGitInitRunner:
    """Host runner for functional tests only; it is not a sandbox implementation."""

    def run_git_init(self, *, plan, workspace, empty_template, timeout_seconds):
        completed = subprocess.run(
            [
                plan.git_executable,
                "-C",
                str(workspace),
                "init",
                "--quiet",
                "--initial-branch",
                plan.initial_branch,
                "--template",
                str(empty_template),
                "--",
                str(workspace),
            ],
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
            },
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ProcessResult(
            status="exited",
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def test_empty_workspace_builds_plan_for_default_main_branch(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    service = GitRepositoryInitService(workspace)

    plan = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")

    assert plan.initial_branch == "main"
    assert plan.repository_root == str(workspace.resolve())
    assert plan.target_kind == "empty_directory"
    assert plan.target_device is not None
    assert plan.target_inode is not None


def test_existing_non_repository_files_are_bound_into_plan(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "main.py").write_text("print('hello')\n", encoding="utf-8")
    service = GitRepositoryInitService(workspace)

    plan = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")

    assert plan.target_kind == "existing_non_repository_directory"
    assert len(plan.target_listing_hash) == 64


def test_plan_identity_and_sandbox_grant_hash_are_stable_for_same_action(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    service = GitRepositoryInitService(workspace)

    first = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")
    second = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")

    assert first.plan_id == second.plan_id
    assert first.sandbox_grant_hash == second.sandbox_grant_hash


@pytest.mark.parametrize("branch", ["-option", "bad..name", "a.lock", "bad name", "x\nname"])
def test_invalid_initial_branch_is_rejected_before_plan(tmp_path: Path, branch: str) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()

    with pytest.raises(GitRepositoryInitError, match="git_init_invalid_branch"):
        GitRepositoryInitService(workspace).plan(
            run_id="run-1",
            action_id="action-1",
            workspace_identity="ws-1",
            initial_branch=branch,
        )


def test_verified_existing_repository_is_idempotent_without_initialization(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)

    result = GitRepositoryInitService(workspace).discover(workspace_identity="ws-1")

    assert result.status == GitRepositoryInitStatus.ALREADY_INITIALIZED
    assert result.repository_snapshot is not None
    assert result.repository_snapshot.unborn is True
    assert result.git_identity_available is False
    assert "git_commit" not in result.available_followup_tools
    assert result.followup_blocked_reason == "git_identity_missing"


def test_execution_fails_closed_without_scoped_sandbox_runner(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    service = GitRepositoryInitService(workspace)
    plan = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")

    with pytest.raises(GitRepositoryInitError, match="git_init_backend_unsupported"):
        service.execute(plan, approved=True)

    assert not (workspace / ".git").exists()


def test_test_runner_initializes_and_verifies_without_claiming_sandbox_acceptance(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "main.py").write_text("print('hello')\n", encoding="utf-8")
    service = GitRepositoryInitService(workspace, runner=_TestOnlyGitInitRunner())
    plan = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")

    result = service.execute(plan, approved=True)

    assert result.status == GitRepositoryInitStatus.INITIALIZED
    assert result.repository_snapshot is not None
    assert result.repository_snapshot.branch == "main"
    assert result.repository_snapshot.unborn is True
    assert result.git_identity_available is False
    assert "git_commit" not in result.available_followup_tools
    assert (workspace / "main.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_target_listing_change_invalidates_plan_before_runner(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    service = GitRepositoryInitService(workspace)
    plan = service.plan(run_id="run-1", action_id="action-1", workspace_identity="ws-1")
    (workspace / "appeared.txt").write_text("change\n", encoding="utf-8")

    with pytest.raises(GitRepositoryInitError, match="git_init_plan_stale"):
        service.execute(plan, approved=True)

    assert not (workspace / ".git").exists()


def test_symlink_workspace_is_rejected(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)

    with pytest.raises(GitRepositoryInitError, match="git_init_target_unsafe"):
        GitRepositoryInitService(linked).plan(
            run_id="run-1", action_id="action-1", workspace_identity="ws-1"
        )


def test_symlink_parent_of_workspace_is_rejected(tmp_path: Path) -> None:
    actual_parent = tmp_path / "actual-parent"
    actual_parent.mkdir()
    workspace = actual_parent / "project"
    workspace.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(actual_parent, target_is_directory=True)

    with pytest.raises(GitRepositoryInitError, match="git_init_target_unsafe"):
        GitRepositoryInitService(linked_parent / "project").plan(
            run_id="run-1", action_id="action-1", workspace_identity="ws-1"
        )


def test_workspace_inside_parent_repository_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    subprocess.run(["git", "init", "--quiet", str(parent)], check=True)
    nested = parent / "project"
    nested.mkdir()

    with pytest.raises(GitRepositoryInitError, match="git_init_nested_repository"):
        GitRepositoryInitService(nested).plan(
            run_id="run-1", action_id="action-1", workspace_identity="ws-1"
        )
