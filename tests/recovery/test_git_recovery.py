from __future__ import annotations

from pathlib import Path

import pytest

from tests.git.conftest import run_git
from tests.recovery.helpers import make_snapshot
from vera.contracts.recovery import RecoveryClassification, RecoveryStage
from vera.git.commit import GitCommitter, GitCommitTransactionError
from vera.git.commit_plan import GitCommitPlanBuilder
from vera.git.service import GitService
from vera.recovery.classifier import RecoveryClassifier
from vera.recovery.git import classify_commit_recovery
from vera.recovery.models import PendingGitOperation


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
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


def test_commit_recovery_stops_when_head_has_an_unrelated_third_party_commit(
    git_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "app.py").write_text("planned\n", encoding="utf-8")
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
    (repository / "other.txt").write_text("third party\n", encoding="utf-8")
    run_git(repository, "add", "--", "other.txt", env=env)
    run_git(repository, "commit", "--quiet", "-m", "third party", env=env)

    with pytest.raises(GitCommitTransactionError) as caught:
        GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add app")

    assert caught.value.code == "manual_required"
    assert run_git(repository, "log", "-1", "--format=%s", env=env).strip() == "third party"


@pytest.mark.parametrize(
    ("current_head", "result_proven", "state"),
    [("old", False, "retry"), ("new", True, "recovered"), ("new", False, "manual_required")],
)
def test_commit_recovery_classifier_has_explicit_terminal_states(
    current_head: str, result_proven: bool, state: str
) -> None:
    decision = classify_commit_recovery(
        plan_id="plan-1",
        current_head=current_head,
        expected_head="old",
        result_proven=result_proven,
    )

    assert decision.state == state


def test_pending_git_operation_is_private_snapshot_fact_and_resumable() -> None:
    snapshot = make_snapshot(Path("/tmp/vera-recovery-test"), stage=RecoveryStage.STARTED)
    pending = PendingGitOperation(
        operation="git_commit",
        plan_id="plan-1",
        run_id=snapshot.run_id,
        expected_head_oid="a" * 40,
        expected_branch="main",
        commit_message_hash="b" * 64,
        paths=("app.py",),
        policy_hash="c" * 64,
    )
    snapshot = snapshot.model_copy(update={"pending_git_operation": pending})

    report = RecoveryClassifier().classify(snapshot, ())

    assert report.classification is RecoveryClassification.MANUAL_REQUIRED
    assert report.reason_code == "git_operation_pending"
    assert "message" not in snapshot.model_dump(mode="json")
