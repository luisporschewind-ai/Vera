from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
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
    )
    return env


def run_git(cwd: Path, *args: str, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


@pytest.fixture
def git_repo(tmp_path: Path, git_env: dict[str, str]) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    root.mkdir()
    run_git(root, "init", "--quiet", env=git_env)
    (root / "README.md").write_text("initial\n", encoding="utf-8")
    run_git(root, "add", "--", "README.md", env=git_env)
    run_git(root, "commit", "--quiet", "-m", "initial", env=git_env)
    return root, git_env
