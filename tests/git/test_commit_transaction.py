from __future__ import annotations

from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.git.commit import GitCommitResult, GitCommitter, GitCommitTransactionError
from vera.git.commit_plan import GitCommitPlanBuilder
from vera.git.service import GitService
from vera.persistence.operation_receipt import OperationReceiptStore, receipt_key


def test_commit_transaction_commits_only_plan_paths_and_preserves_other_staged_content(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (repository / "user.txt").write_text("user staged\n", encoding="utf-8")
    run_git(repository, "add", "--", "user.txt", env=env)
    service = GitService(repository, environment=env)
    plan = GitCommitPlanBuilder(service).build(
        run_id="run-1",
        action_ids=("action-1",),
        workspace_identity="workspace-1",
        paths=("app.py",),
        message="Add app",
        verification_status="passed",
        policy_hash="policy-1",
    )

    result = GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add app")

    assert isinstance(result, GitCommitResult)
    assert result.committed_paths == ("app.py",)
    assert run_git(repository, "show", "--format=%s", "--no-patch", env=env).strip() == "Add app"
    assert run_git(repository, "show", "--format=", "--name-only", env=env).strip() == "app.py"
    assert run_git(repository, "diff", "--cached", "--name-only", env=env).strip() == "user.txt"
    operation_id, _ = receipt_key(
        "git_commit", {"plan_id": plan.plan_id, "message_hash": plan.commit_message_hash}
    )
    receipt = OperationReceiptStore(tmp_path / "state").load("run-1", operation_id)
    assert receipt is not None
    assert receipt.operation == "git_commit"


def test_commit_transaction_rejects_stale_worktree_before_staging(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "app.py").write_text("first\n", encoding="utf-8")
    service = GitService(repository, environment=env)
    plan = GitCommitPlanBuilder(service).build(
        run_id="run-1",
        action_ids=("action-1",),
        workspace_identity="workspace-1",
        paths=("app.py",),
        message="Add app",
        verification_status="passed",
        policy_hash="policy-1",
    )
    (repository / "app.py").write_text("changed after plan\n", encoding="utf-8")

    with pytest.raises(GitCommitTransactionError) as caught:
        GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add app")

    assert caught.value.code == "git_plan_stale"
    assert run_git(repository, "diff", "--cached", "--name-only", env=env) == ""


def test_commit_transaction_accepts_multiple_plan_paths_in_any_requested_order(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "b.txt").write_text("b\n", encoding="utf-8")
    (repository / "a.txt").write_text("a\n", encoding="utf-8")
    service = GitService(repository, environment=env)
    plan = GitCommitPlanBuilder(service).build(
        run_id="run-1",
        action_ids=("action-1", "action-2"),
        workspace_identity="workspace-1",
        paths=("b.txt", "a.txt"),
        message="Add two files",
        verification_status="passed",
        policy_hash="policy-1",
    )

    result = GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add two files")

    assert result.committed_paths == ("b.txt", "a.txt")
    assert set(run_git(repository, "show", "--format=", "--name-only", env=env).split()) == {
        "a.txt",
        "b.txt",
    }


def test_commit_transaction_restores_index_when_commit_fails(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "user.txt").write_text("user staged\n", encoding="utf-8")
    run_git(repository, "add", "--", "user.txt", env=env)
    (repository / "app.py").write_text("print('changed')\n", encoding="utf-8")
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o700)
    index_path = Path(run_git(repository, "rev-parse", "--git-path", "index", env=env).strip())
    if not index_path.is_absolute():
        index_path = repository / index_path
    before_index = index_path.read_bytes()
    service = GitService(repository, environment=env)
    plan = GitCommitPlanBuilder(service).build(
        run_id="run-1",
        action_ids=("action-1",),
        workspace_identity="workspace-1",
        paths=("app.py",),
        message="Add app",
        verification_status="passed",
        policy_hash="policy-1",
    )

    with pytest.raises(GitCommitTransactionError) as caught:
        GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add app")

    assert caught.value.code == "git_commit_failed"
    assert index_path.read_bytes() == before_index
    assert run_git(repository, "diff", "--cached", "--name-only", env=env).strip() == "user.txt"


def test_commit_transaction_handles_literal_special_paths(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    paths = ("-dash.txt", "space name.txt", "unicode-猫.txt")
    for path in paths:
        (repository / path).write_text(f"{path}\n", encoding="utf-8")
    service = GitService(repository, environment=env)
    plan = GitCommitPlanBuilder(service).build(
        run_id="run-1",
        action_ids=("action-1",),
        workspace_identity="workspace-1",
        paths=paths,
        message="Add literal paths",
        verification_status="passed",
        policy_hash="policy-1",
    )

    result = GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add literal paths")

    assert result.committed_paths == paths
    assert set(
        run_git(repository, "ls-tree", "-r", "--name-only", "-z", "HEAD", env=env).split("\0")
    ) >= set(paths)
