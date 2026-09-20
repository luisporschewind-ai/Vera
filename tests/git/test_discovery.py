from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.git.discovery import GitDiscovery, GitDiscoveryError


def test_discovers_repository_root_and_workspace_prefix(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    workspace = repository / "packages" / "demo"
    workspace.mkdir(parents=True)

    discovered = GitDiscovery(workspace, environment=env).discover()

    assert discovered.repository_root == str(repository.resolve())
    assert discovered.workspace_prefix == "packages/demo"
    assert discovered.git_dir == str((repository / ".git").resolve())
    assert discovered.bare is False


def test_non_repository_is_rejected_without_parent_search(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(GitDiscoveryError) as caught:
        GitDiscovery(workspace).discover()

    assert caught.value.code == "git_not_repository"


def test_bare_repository_is_unsupported(tmp_path: Path, git_env: dict[str, str]) -> None:
    bare = tmp_path / "bare.git"
    bare.mkdir()
    import subprocess

    subprocess.run(
        ["git", "init", "--bare", "--quiet", str(bare)],
        env=git_env,
        check=True,
        capture_output=True,
    )

    with pytest.raises(GitDiscoveryError) as caught:
        GitDiscovery(bare, environment=git_env).discover()

    assert caught.value.code == "git_unsupported_state"


def test_nested_repository_does_not_expand_workspace_root(
    git_repo: tuple[Path, dict[str, str]],
) -> None:
    repository, env = git_repo
    nested = repository / "nested"
    nested.mkdir()
    import subprocess

    subprocess.run(
        ["git", "init", "--quiet", str(nested)],
        env=env,
        check=True,
        capture_output=True,
    )

    discovered = GitDiscovery(repository, environment=env).discover()

    assert discovered.repository_root == str(repository.resolve())
    assert discovered.workspace_prefix == "."


def test_discovers_linked_worktree_git_file_without_using_workspace_parent(
    git_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = git_repo
    linked = tmp_path / "linked"
    import subprocess

    subprocess.run(
        ["git", "-C", str(repository), "worktree", "add", "--quiet", str(linked), "HEAD"],
        env=env,
        check=True,
        capture_output=True,
    )

    git_file = linked / ".git"
    assert git_file.is_file()
    discovered = GitDiscovery(linked, environment=env).discover()

    assert discovered.repository_root == str(linked.resolve())
    assert discovered.workspace_prefix == "."
    assert discovered.git_dir != str(git_file.resolve())


def test_submodule_and_sparse_checkout_are_explicitly_unsupported(
    git_repo: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    repository, env = git_repo
    nested_source = tmp_path / "nested-source"
    nested_source.mkdir()
    import subprocess

    subprocess.run(
        ["git", "init", "--quiet", str(nested_source)],
        env=env,
        check=True,
        capture_output=True,
    )
    (nested_source / "module.txt").write_text("module\n", encoding="utf-8")
    run_git(nested_source, "add", "--", "module.txt", env=env)
    run_git(nested_source, "commit", "--quiet", "-m", "module", env=env)
    run_git(
        repository,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "--quiet",
        str(nested_source),
        "module",
        env=env,
    )

    with pytest.raises(GitDiscoveryError) as submodule_error:
        GitDiscovery(repository / "module", environment=env).discover()
    assert submodule_error.value.code == "git_unsupported_state"

    run_git(repository, "config", "core.sparseCheckout", "true", env=env)
    with pytest.raises(GitDiscoveryError) as sparse_error:
        GitDiscovery(repository, environment=env).discover()
    assert sparse_error.value.code == "git_unsupported_state"
