import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "hello.txt").write_text("old\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "vera-tests@example.invalid")
    git(repo, "config", "user.name", "Vera Tests")
    git(repo, "add", "hello.txt")
    git(repo, "commit", "-qm", "fixture")
    return repo
