"""Run already-approved verification commands without a shell."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessResult, ProcessSupervisor
from vera.verification.artifacts import (
    VerificationArtifactError,
    VerificationArtifactRoot,
    environment_for_plan,
    with_workspace_runtime_path,
)


def workspace_file_fingerprint(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                digest = "unreadable"
            files[relative] = digest
    return files


def git_porcelain(root: Path) -> str:
    if not (root / ".git").exists():
        return ""
    environment = build_child_environment(
        purpose="verification",
        overrides={"GIT_OPTIONAL_LOCKS": "0"},
    ).values
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    return completed.stdout


class VerificationRunner:
    def __init__(
        self,
        workspace_root: Path,
        max_output_bytes: int = 100_000,
        allowed_environment: tuple[str, ...] = (),
        supervisor: ProcessSupervisor | None = None,
        *,
        artifact_prefix: Path | None = None,
        artifact_roots: VerificationArtifactRoot | None = None,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.max_output_bytes = max_output_bytes
        self.allowed_environment = allowed_environment
        self._supervisor = supervisor or ProcessSupervisor()
        self._roots = artifact_roots or VerificationArtifactRoot(prefix=artifact_prefix)

    def _cwd(self, command: VerificationCommand) -> Path:
        candidate = (self.workspace_root / command.cwd).resolve()
        candidate.relative_to(self.workspace_root)
        if not candidate.is_dir():
            raise ValueError("verification cwd is not a directory")
        return candidate

    def _result(
        self,
        command: VerificationCommand,
        started: datetime,
        monotonic_start: float,
        status: str,
        exit_code: int | None,
        stdout: bytes = b"",
        stderr: bytes = b"",
        stdout_truncated: bool = False,
        stderr_truncated: bool = False,
        reason_code: str | None = None,
        artifact_cleanup_status: str | None = None,
        workspace_mutations: tuple[str, ...] = (),
    ) -> VerificationResult:
        stdout_truncated = stdout_truncated or len(stdout) > self.max_output_bytes
        stderr_truncated = stderr_truncated or len(stderr) > self.max_output_bytes
        plan = command.artifact_plan
        return VerificationResult(
            argv=command.argv,
            cwd=command.cwd,
            started_at=started,
            completed_at=datetime.now(UTC),
            duration_seconds=max(0.0, time.monotonic() - monotonic_start),
            exit_code=exit_code,
            stdout=stdout[: self.max_output_bytes].decode("utf-8", errors="replace"),
            stderr=stderr[: self.max_output_bytes].decode("utf-8", errors="replace"),
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            status=status,  # type: ignore[arg-type]
            artifact_profile=None if plan is None else plan.profile,
            artifact_root=None if plan is None else plan.root,
            artifact_cleanup_status=artifact_cleanup_status,  # type: ignore[arg-type]
            workspace_mutations=workspace_mutations,
            reason_code=reason_code,
        )

    def run(
        self,
        command: VerificationCommand,
        *,
        cancel_event: threading.Event | None = None,
    ) -> VerificationResult:
        started = datetime.now(UTC)
        monotonic_start = time.monotonic()
        plan = command.artifact_plan
        if plan is None:
            return self._result(
                command,
                started,
                monotonic_start,
                "rejected",
                None,
                reason_code="verification_not_planned",
                artifact_cleanup_status="skipped",
            )
        try:
            cwd = self._cwd(command)
        except (OSError, ValueError) as exc:
            return self._result(
                command,
                started,
                monotonic_start,
                "rejected",
                None,
                stderr=str(exc).encode(),
                reason_code="cwd_forbidden",
                artifact_cleanup_status="skipped",
            )
        if plan.root:
            try:
                self._roots.prepare_existing(Path(plan.root), workspace_root=self.workspace_root)
            except VerificationArtifactError:
                return self._result(
                    command,
                    started,
                    monotonic_start,
                    "rejected",
                    None,
                    reason_code="verification_artifact_root_unsafe",
                    artifact_cleanup_status="skipped",
                )
        before = workspace_file_fingerprint(self.workspace_root)
        before_git = git_porcelain(self.workspace_root)
        environment = with_workspace_runtime_path(
            build_child_environment(
                purpose="verification",
                overrides=environment_for_plan(plan),
                extra_allow_names=self.allowed_environment,
            ).values,
            self.workspace_root,
        )
        completed = self._supervisor.run(
            ProcessRequest(
                argv=command.argv,
                cwd=cwd,
                env=environment,
                timeout_seconds=min(command.timeout_seconds, 120),
                max_output_bytes=self.max_output_bytes,
            ),
            cancel_event=cancel_event,
        )
        mutations = _mutations(
            before,
            workspace_file_fingerprint(self.workspace_root),
            before_git,
            git_porcelain(self.workspace_root),
        )
        cleanup_status = "skipped"
        cleanup_code: str | None = None
        if plan.root:
            cleanup = self._roots.cleanup(plan.root, workspace_root=self.workspace_root)
            cleanup_status = cleanup.status
            cleanup_code = cleanup.code
        return self._finish(
            command,
            started,
            monotonic_start,
            completed,
            cleanup_status=cleanup_status,
            cleanup_code=cleanup_code,
            mutations=mutations,
        )

    def _finish(
        self,
        command: VerificationCommand,
        started: datetime,
        monotonic_start: float,
        completed: ProcessResult,
        *,
        cleanup_status: str,
        cleanup_code: str | None,
        mutations: tuple[str, ...],
    ) -> VerificationResult:
        status = _process_status(completed)
        exit_code = completed.exit_code if completed.status == "exited" else None
        reason_code: str | None = None
        if mutations:
            status = "workspace_polluted"
            reason_code = "workspace_polluted"
        if cleanup_status == "failed":
            reason_code = cleanup_code or "artifact_cleanup_failed"
            if status == "passed":
                status = "error"
        return self._result(
            command,
            started,
            monotonic_start,
            status,
            exit_code,
            completed.stdout,
            completed.stderr,
            completed.stdout_truncated,
            completed.stderr_truncated,
            reason_code=reason_code,
            artifact_cleanup_status=cleanup_status,
            workspace_mutations=mutations,
        )


def _process_status(completed: ProcessResult) -> str:
    if completed.status == "timed_out":
        return "timed_out"
    if completed.status == "cancelled":
        return "cancelled"
    if completed.status == "error":
        return "error"
    if completed.exit_code == 0:
        return "passed"
    return "failed"


def _mutations(
    before: dict[str, str],
    after: dict[str, str],
    before_git: str,
    after_git: str,
) -> tuple[str, ...]:
    changed = sorted(
        set(before) ^ set(after) | {path for path in after if before.get(path) != after.get(path)}
    )
    if before_git != after_git and not changed:
        return ("git-status",)
    return tuple(changed)
