"""Process identity for Vera installs. Never probe the user workspace git."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_metadata_version
from pathlib import Path
from subprocess import CompletedProcess
from typing import Protocol

from vera import __version__

_GIT_TIMEOUT_SECONDS = 1.0


class GitRun(Protocol):
    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float,
    ) -> CompletedProcess[str]: ...


@dataclass(frozen=True)
class VersionIdentity:
    name: str
    version: str
    location: str
    install: str
    git_commit: str | None = None
    git_dirty: bool | None = None

    @property
    def display_version(self) -> str:
        if not self.git_commit:
            return self.version
        local = self.git_commit
        if self.git_dirty:
            local = f"{local}.dirty"
        return f"{self.version}+{local}"

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "version": self.version,
            "display_version": self.display_version,
            "location": self.location,
            "install": self.install,
        }
        if self.git_commit is not None:
            payload["git"] = {"commit": self.git_commit, "dirty": bool(self.git_dirty)}
        return payload

    def to_text(self) -> str:
        lines = [
            f"vera {self.display_version}",
            f"location: {self.location}",
            f"install: {self.install}",
        ]
        if self.git_commit is not None:
            dirty = "dirty" if self.git_dirty else "clean"
            lines.append(f"git: {self.git_commit} · {dirty}")
        return "\n".join(lines)

    def doctor_detail(self) -> str:
        return f"{self.display_version} · {self.install} · {self.location}"


def _metadata_version() -> str:
    try:
        return package_metadata_version("vera-agent")
    except PackageNotFoundError:
        return __version__
    except Exception:
        return __version__


def _classify_install(package_dir: Path) -> tuple[str, Path | None]:
    src = package_dir.parent
    root = src.parent
    if src.name == "src" and package_dir.name == "vera" and (root / "pyproject.toml").is_file():
        return "editable", root
    if "site-packages" in package_dir.parts:
        return "wheel", None
    return "unknown", None


def _run_git(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float,
) -> CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _source_git(
    root: Path,
    git_run: GitRun,
) -> tuple[str | None, bool | None]:
    if not (root / ".git").exists():
        return None, None
    commit_argv = ("git", "-C", str(root), "rev-parse", "--short", "HEAD")
    status_argv = ("git", "-C", str(root), "status", "--porcelain=v1")
    try:
        commit_result = git_run(commit_argv, cwd=root, timeout=_GIT_TIMEOUT_SECONDS)
    except Exception:
        return None, None
    commit: str | None = None
    if commit_result.returncode == 0:
        text = commit_result.stdout.strip()
        commit = text or None
    if commit is None:
        return None, None
    try:
        status_result = git_run(status_argv, cwd=root, timeout=_GIT_TIMEOUT_SECONDS)
    except Exception:
        return commit, None
    dirty: bool | None = None
    if status_result.returncode == 0:
        dirty = bool(status_result.stdout.strip())
    return commit, dirty


def inspect_version_identity(
    *,
    package_file: Path | None = None,
    package_version: str | None = None,
    git_run: GitRun | None = None,
) -> VersionIdentity:
    if package_file is None:
        package_dir = Path(__file__).resolve().parent
    else:
        package_dir = package_file.resolve().parent
    install, source_root = _classify_install(package_dir)
    commit: str | None = None
    dirty: bool | None = None
    if source_root is not None:
        commit, dirty = _source_git(source_root, git_run or _run_git)
    return VersionIdentity(
        name="vera",
        version=package_version or _metadata_version(),
        location=str(package_dir),
        install=install,
        git_commit=commit,
        git_dirty=dirty,
    )


def current_identity() -> VersionIdentity:
    return inspect_version_identity()


def current_display_version() -> str:
    try:
        display = current_identity().display_version
    except Exception:
        return "unavailable"
    return display or "unavailable"
