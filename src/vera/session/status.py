"""UI-independent workspace and session status probing."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess
from typing import Protocol

from vera.session.models import (
    ConversationStats,
    GitStatus,
    PermissionStatus,
    SessionStatus,
)
from vera.version import current_display_version


class GitRunner(Protocol):
    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CompletedProcess[str]: ...


class SubprocessGitRunner:
    """Run only the fixed read-only Git argv tuples used by status probes."""

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )


class WorkspaceStatusProbe:
    def __init__(self, git_runner: GitRunner | None = None) -> None:
        self._git: GitRunner = git_runner or SubprocessGitRunner()

    def inspect(self, workspace: Path) -> GitStatus:
        root = workspace.resolve()
        branch_argv = ("git", "-C", str(root), "symbolic-ref", "--short", "HEAD")
        status_argv = ("git", "-C", str(root), "status", "--porcelain=v1")
        try:
            branch_result = self._git.run(branch_argv, cwd=root, timeout=3)
        except Exception:
            branch_result = None
        try:
            status_result = self._git.run(status_argv, cwd=root, timeout=3)
        except Exception:
            status_result = None

        if branch_result is not None and branch_result.returncode == 128:
            return GitStatus(available=False, branch=None, dirty=None)
        if status_result is not None and status_result.returncode == 128:
            return GitStatus(available=False, branch=None, dirty=None)
        if branch_result is None and status_result is None:
            return GitStatus(available=False, branch=None, dirty=None)

        branch: str | None = None
        if branch_result is not None and branch_result.returncode == 0:
            text = branch_result.stdout.strip()
            branch = text or None

        dirty: bool | None = None
        if status_result is not None and status_result.returncode == 0:
            dirty = bool(status_result.stdout.strip())

        return GitStatus(available=True, branch=branch, dirty=dirty)


def _package_version() -> str:
    return current_display_version()


class SessionStatusService:
    def __init__(
        self,
        *,
        version_reader: Callable[[], str] | None = None,
        git_runner: GitRunner | None = None,
    ) -> None:
        self._version_reader = version_reader or _package_version
        self._probe = WorkspaceStatusProbe(git_runner)

    def snapshot(
        self,
        *,
        workspace: Path,
        model_profile: str,
        model_name: str,
        conversation: ConversationStats,
        permissions: PermissionStatus,
    ) -> SessionStatus:
        try:
            package_version = self._version_reader()
        except Exception:
            package_version = "unavailable"
        if not package_version:
            package_version = "unavailable"
        return SessionStatus(
            version=package_version,
            model_profile=model_profile,
            model_name=model_name,
            workspace=workspace.resolve(),
            git=self._probe.inspect(workspace),
            context=conversation,
            permissions=permissions,
        )
