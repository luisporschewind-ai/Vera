"""Git repository discovery without assuming a ``.git`` directory layout."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from vera.git.models import GitRepositoryInfo
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessResult, ProcessSupervisor


class GitDiscoveryError(ValueError):
    """Stable failure while locating a supported Git repository."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class GitDiscovery:
    def __init__(
        self,
        workspace: Path,
        *,
        supervisor: ProcessSupervisor | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.supervisor = supervisor or ProcessSupervisor()
        self.environment = dict(environment) if environment is not None else os.environ.copy()
        self.timeout_seconds = timeout_seconds

    def discover(self) -> GitRepositoryInfo:
        if not self.workspace.is_dir():
            raise GitDiscoveryError("git_not_repository", "workspace is not a directory")
        bare_check = self._run(("rev-parse", "--is-bare-repository"))
        if bare_check.status != "exited":
            raise GitDiscoveryError(self._status_code(bare_check), "git discovery did not finish")
        if bare_check.exit_code != 0:
            raise GitDiscoveryError(self._failure_code(bare_check))
        if bare_check.stdout.decode("utf-8", errors="strict").strip() == "true":
            raise GitDiscoveryError("git_unsupported_state", "bare repositories are unsupported")
        result = self._run(
            (
                "rev-parse",
                "--show-toplevel",
                "--absolute-git-dir",
                "--is-bare-repository",
            )
        )
        if result.status != "exited":
            raise GitDiscoveryError(self._status_code(result), "git discovery did not finish")
        if result.exit_code != 0:
            raise GitDiscoveryError(self._failure_code(result))
        lines = result.stdout.decode("utf-8", errors="strict").splitlines()
        if len(lines) != 3 or lines[2] not in {"true", "false"}:
            raise GitDiscoveryError("git_invalid_output", "Git discovery output was invalid")
        repository_root = Path(lines[0]).resolve()
        git_dir = Path(lines[1]).resolve()
        bare = lines[2] == "true"
        if bare:
            raise GitDiscoveryError("git_unsupported_state", "bare repositories are unsupported")
        superproject = self._run(("rev-parse", "--show-superproject-working-tree"))
        if superproject.status != "exited":
            raise GitDiscoveryError(self._status_code(superproject), "git discovery did not finish")
        if superproject.exit_code != 0:
            raise GitDiscoveryError("git_invalid_output", "Git repository state was invalid")
        if superproject.stdout.decode("utf-8", errors="strict").strip():
            raise GitDiscoveryError("git_unsupported_state", "submodules are unsupported")
        sparse = self._run(("config", "--bool", "--get", "core.sparseCheckout"))
        if sparse.status != "exited":
            raise GitDiscoveryError(self._status_code(sparse), "git discovery did not finish")
        if sparse.exit_code not in {0, 1}:
            raise GitDiscoveryError("git_invalid_output", "Git repository state was invalid")
        if sparse.stdout.decode("utf-8", errors="strict").strip() == "true":
            raise GitDiscoveryError("git_unsupported_state", "sparse checkouts are unsupported")
        try:
            prefix = self.workspace.relative_to(repository_root).as_posix()
        except ValueError as exc:
            raise GitDiscoveryError(
                "git_repository_outside_workspace", "repository root is not an ancestor"
            ) from exc
        return GitRepositoryInfo(
            repository_root=str(repository_root),
            workspace_prefix=prefix or ".",
            git_dir=str(git_dir),
            bare=bare,
        )

    def _run(self, arguments: tuple[str, ...]) -> ProcessResult:
        return self.supervisor.run(
            ProcessRequest(
                argv=("git", "-C", str(self.workspace), *arguments),
                cwd=self.workspace,
                env=self._environment(),
                timeout_seconds=self.timeout_seconds,
                max_output_bytes=16_384,
            )
        )

    def _environment(self) -> dict[str, str]:
        return build_child_environment(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
            },
            purpose="git",
            source=self.environment,
        ).values

    @staticmethod
    def _failure_code(result: ProcessResult) -> str:
        # LC_ALL=C is set for discovery. Do not mistake launcher or access errors
        # for repository absence, and never use stderr as an instruction to retry.
        error = result.stderr.lower()
        if b"operation not permitted" in error or b"permission denied" in error:
            return "git_permission_denied"
        if b"xcode-select:" in error or b"xcrun:" in error:
            return "git_toolchain_unavailable"
        if error.startswith(b"fatal: not a git repository"):
            return "git_not_repository"
        return "git_process_error"

    @staticmethod
    def _status_code(result: ProcessResult) -> str:
        if result.status == "timed_out":
            return "git_timeout"
        if result.status == "cancelled":
            return "git_cancelled"
        return "git_process_error"
