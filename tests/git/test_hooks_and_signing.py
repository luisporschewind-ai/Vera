from __future__ import annotations

import hashlib
from pathlib import Path

from tests.git.conftest import run_git
from vera.git.commit import GitCommitter, GitCommitTransactionError
from vera.git.commit_plan import GitCommitPlanBuilder
from vera.git.hooks import GitHookInspector
from vera.git.service import GitService


def test_hook_facts_cover_default_hooks_and_content_changes(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o700)
    service = GitService(repository, environment=env)
    inspector = GitHookInspector(service)

    first = inspector.inspect()
    entry = next(item for item in first.hooks if item.name == "pre-commit")
    assert entry.relative_path == ".git/hooks/pre-commit"
    assert entry.content_hash == hashlib.sha256(hook.read_bytes()).hexdigest()
    assert entry.executable is True

    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    second = inspector.inspect()
    assert second.facts_hash != first.facts_hash
    assert second.hooks[0].content_hash != entry.content_hash


def test_hook_facts_follow_core_hooks_path_and_reject_symlink_execution(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    custom = repository / ".vera-hooks"
    custom.mkdir()
    target = repository / "target-hook"
    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    target.chmod(0o700)
    (custom / "commit-msg").symlink_to(target)
    run_git(repository, "config", "core.hooksPath", ".vera-hooks", env=env)

    facts = GitHookInspector(GitService(repository, environment=env)).inspect()

    entry = next(item for item in facts.hooks if item.name == "commit-msg")
    assert entry.relative_path == ".vera-hooks/commit-msg"
    assert entry.executable is False


def test_signing_facts_detect_existing_noninteractive_configuration(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "commit.gpgSign", "true", env=env)
    run_git(repository, "config", "gpg.format", "ssh", env=env)
    run_git(repository, "config", "user.signingKey", "ssh-ed25519 AAAA", env=env)

    facts = GitHookInspector(GitService(repository, environment=env)).signing_facts()

    assert facts.configured is True
    assert facts.format == "ssh"
    assert facts.key_configured is True
    assert "AAAA" not in facts.facts_hash


def test_commit_hook_changes_outside_plan_are_rejected(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nprintf 'hook\n' > outside.txt\n", encoding="utf-8")
    hook.chmod(0o700)
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

    try:
        GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add app")
    except GitCommitTransactionError as exc:
        assert exc.code == "git_hook_changed_scope"
    else:
        raise AssertionError("hook scope change must be rejected")


def test_unavailable_existing_signing_configuration_is_stable_error(
    git_repo: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    repository, env = git_repo
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    signer = repository / "fail-gpg"
    signer.write_text(
        "#!/bin/sh\necho 'gpg failed to sign the data' >&2\nexit 1\n", encoding="utf-8"
    )
    signer.chmod(0o700)
    run_git(repository, "config", "commit.gpgSign", "true", env=env)
    run_git(repository, "config", "gpg.program", str(signer), env=env)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
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

    try:
        GitCommitter(service, state_dir=tmp_path / "state").execute(plan, "Add app")
    except GitCommitTransactionError as exc:
        assert exc.code == "git_signing_unavailable"
    else:
        raise AssertionError("unavailable signing must be reported")
    assert run_git(repository, "config", "--get", "commit.gpgSign", env=env).strip() == "true"
