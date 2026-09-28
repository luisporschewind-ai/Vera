from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.git.models import GitDiffRequest, GitLogRequest, GitShowRequest
from vera.git.service import GitService, GitServiceError


def test_status_and_diff_are_workspace_bounded(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    workspace = repository / "packages" / "demo"
    workspace.mkdir(parents=True)
    (workspace / "app.py").write_text("print('base')\n", encoding="utf-8")
    run_git(repository, "add", "--", "packages/demo/app.py", env=env)
    run_git(repository, "commit", "--quiet", "-m", "add app", env=env)
    (workspace / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (workspace / "-scratch.txt").write_text("untracked\n", encoding="utf-8")
    (repository / "README.md").write_text("outside change\n", encoding="utf-8")

    service = GitService(workspace, environment=env)
    snapshot = service.status()
    diff = service.diff(GitDiffRequest(scope="working"))

    assert snapshot.workspace_prefix == "packages/demo"
    assert {entry.path for entry in snapshot.entries} == {"app.py", "-scratch.txt"}
    assert diff.files == ("app.py",)
    assert "changed" in diff.patch
    assert "README.md" not in diff.patch
    assert str(repository) not in diff.patch


def test_log_show_and_branches_are_structured_and_bounded(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    workspace = repository / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello\n", encoding="utf-8")
    run_git(repository, "add", "--", "workspace/note.txt", env=env)
    run_git(repository, "commit", "--quiet", "-m", "second", env=env)
    service = GitService(workspace, environment=env)

    commits = service.log(GitLogRequest(limit=20))
    shown = service.show(GitShowRequest(ref=commits[0].oid))
    branches = service.branches()

    assert commits[0].subject == "second"
    assert commits[0].oid == shown.commit.oid
    assert "note.txt" in shown.files
    assert shown.diff.scope == "range"
    assert any(branch.current for branch in branches)
    assert all(branch.ahead >= 0 and branch.behind >= 0 for branch in branches)


def test_git_read_requests_reject_path_escape_and_invalid_range(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    workspace = repository / "workspace"
    workspace.mkdir()
    service = GitService(workspace, environment=env)

    with pytest.raises(GitServiceError) as path_error:
        service.diff(GitDiffRequest(scope="working", paths=("../README.md",)))
    with pytest.raises(GitServiceError) as range_error:
        service.diff(GitDiffRequest(scope="range"))

    assert path_error.value.code == "git_path_escape"
    assert range_error.value.code == "git_invalid_request"


def test_status_exposes_unborn_detached_and_operation_states(
    tmp_path: Path, git_env: dict[str, str]
) -> None:
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    run_git(unborn, "init", "--quiet", env=git_env)
    unborn_status = GitService(unborn, environment=git_env).status()
    assert unborn_status.unborn is True
    assert unborn_status.head_oid is None

    repository, env = _make_status_repository(tmp_path, git_env)
    run_git(repository, "checkout", "--quiet", "--detach", "HEAD", env=env)
    detached = GitService(repository, environment=env).status()
    assert detached.detached is True
    assert detached.branch is None

    (repository / ".git" / "MERGE_HEAD").write_text("deadbeef\n", encoding="ascii")
    operation = GitService(repository, environment=env).status()
    assert operation.operation_state == "merge"


def test_diff_and_show_return_binary_file_summary_without_binary_payload(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    binary = repository / "blob.bin"
    binary.write_bytes(b"\x00\x01\x02\x03")
    run_git(repository, "add", "--", "blob.bin", env=env)
    run_git(repository, "commit", "--quiet", "-m", "binary", env=env)

    binary.write_bytes(b"\x00\xff\x10\x11")
    service = GitService(repository, environment=env)
    working = service.diff(GitDiffRequest(scope="working"))
    shown = service.show(GitShowRequest(ref="HEAD"))

    assert working.binary_files == ("blob.bin",)
    assert shown.diff.binary_files == ("blob.bin",)
    assert "Binary files" in working.patch


def _make_status_repository(tmp_path: Path, env: dict[str, str]) -> tuple[Path, dict[str, str]]:
    repository = tmp_path / "status-repository"
    repository.mkdir()
    run_git(repository, "init", "--quiet", env=env)
    (repository / "README.md").write_text("base\n", encoding="utf-8")
    run_git(repository, "add", "--", "README.md", env=env)
    run_git(repository, "commit", "--quiet", "-m", "initial", env=env)
    return repository, env
