"""Run already-approved verification commands without a shell."""

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.verification import VerificationCommand, VerificationResult
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessSupervisor


class VerificationRunner:
    def __init__(
        self,
        workspace_root: Path,
        max_output_bytes: int = 100_000,
        allowed_environment: tuple[str, ...] = (),
        supervisor: ProcessSupervisor | None = None,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.max_output_bytes = max_output_bytes
        self.allowed_environment = allowed_environment
        self._supervisor = supervisor or ProcessSupervisor()

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
    ) -> VerificationResult:
        stdout_truncated = stdout_truncated or len(stdout) > self.max_output_bytes
        stderr_truncated = stderr_truncated or len(stderr) > self.max_output_bytes
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
        )

    def run(
        self,
        command: VerificationCommand,
        *,
        cancel_event: threading.Event | None = None,
    ) -> VerificationResult:
        started = datetime.now(UTC)
        monotonic_start = time.monotonic()
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
            )
        environment = build_child_environment(
            purpose="verification",
            extra_allow_names=self.allowed_environment,
        ).values
        timeout = min(command.timeout_seconds, 120)
        completed = self._supervisor.run(
            ProcessRequest(
                argv=command.argv,
                cwd=cwd,
                env=environment,
                timeout_seconds=timeout,
                max_output_bytes=self.max_output_bytes,
            ),
            cancel_event=cancel_event,
        )
        if completed.status == "timed_out":
            status = "timed_out"
        elif completed.status == "cancelled":
            status = "cancelled"
        elif completed.status == "error":
            status = "error"
        elif completed.exit_code == 0:
            status = "passed"
        else:
            status = "failed"
        return self._result(
            command,
            started,
            monotonic_start,
            status,
            completed.exit_code if completed.status == "exited" else None,
            completed.stdout,
            completed.stderr,
            completed.stdout_truncated,
            completed.stderr_truncated,
        )
