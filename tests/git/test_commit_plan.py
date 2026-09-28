from __future__ import annotations

from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.git.commit_plan import GitCommitPlanBuilder, GitCommitPlanError
from vera.git.service import GitService


def test_commit_plan_binds_head_index_paths_message_and_policy(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    (repository / "app.py").write_text("print('changed')\n", encoding="utf-8")
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

    assert plan.run_id == "run-1"
    assert plan.paths == ("app.py",)
    assert plan.branch == "master" or plan.branch == "main"
    assert len(plan.head_oid) == 40
    assert plan.before_hashes["app.py"] != plan.after_hashes["app.py"]
    assert len(plan.index_fingerprint) == 64
    assert len(plan.staged_diff_hash) == 64
    assert len(plan.commit_message_hash) == 64
    assert plan.policy_hash == "policy-1"


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("empty_paths", "git_invalid_request"),
        ("outside_path", "git_path_escape"),
        ("verification_failed", "git_verification_failed"),
        ("empty_message", "git_invalid_message"),
    ],
)
def test_commit_plan_rejects_unsafe_or_unverifiable_requests(
    git_repo: tuple[Path, dict[str, str]], mutation: str, error_code: str
) -> None:
    repository, env = git_repo
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
    service = GitService(repository, environment=env)
    paths = {
        "empty_paths": (),
        "outside_path": ("../README.md",),
        "verification_failed": ("app.py",),
        "empty_message": ("app.py",),
    }[mutation]
    with pytest.raises(GitCommitPlanError) as caught:
        GitCommitPlanBuilder(service).build(
            run_id="run-1",
            action_ids=("action-1",),
            workspace_identity="workspace-1",
            paths=paths,
            message="" if mutation == "empty_message" else "Change",
            verification_status="failed" if mutation == "verification_failed" else "passed",
            policy_hash="policy-1",
        )
    assert caught.value.code == error_code


def test_commit_plan_rejects_existing_staged_target(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    (repository / "app.py").write_text("staged\n", encoding="utf-8")
    run_git(repository, "add", "--", "app.py", env=env)
    service = GitService(repository, environment=env)

    with pytest.raises(GitCommitPlanError) as caught:
        GitCommitPlanBuilder(service).build(
            run_id="run-1",
            action_ids=("action-1",),
            workspace_identity="workspace-1",
            paths=("app.py",),
            message="Commit staged",
            verification_status="passed",
            policy_hash="policy-1",
        )

    assert caught.value.code == "git_target_already_staged"
