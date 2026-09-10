"""Run already-approved verification commands without a shell."""

import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.verification import VerificationCommand, VerificationResult


class VerificationRunner:
    def __init__(
        self,
        workspace_root: Path,
        max_output_bytes: int = 100_000,
        allowed_environment: tuple[str, ...] = (),
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.max_output_bytes = max_output_bytes
        self.allowed_environment = allowed_environment

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
    ) -> VerificationResult:
        stdout_truncated = len(stdout) > self.max_output_bytes
        stderr_truncated = len(stderr) > self.max_output_bytes
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

    @staticmethod
    def _bytes(value: bytes | str | None) -> bytes:
        if value is None:
            return b""
        return value if isinstance(value, bytes) else value.encode()

    def run(self, command: VerificationCommand) -> VerificationResult:
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
        environment_names = {"PATH", "LANG", "LC_ALL", "TMPDIR", *self.allowed_environment}
        environment = {key: value for key, value in os.environ.items() if key in environment_names}
        timeout = min(command.timeout_seconds, 120)
        try:
            completed = subprocess.run(
                list(command.argv),
                cwd=cwd,
                env=environment,
                shell=False,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._bytes(exc.stdout)
            stderr = self._bytes(exc.stderr)
            return self._result(
                command, started, monotonic_start, "timed_out", None, stdout, stderr
            )
        except OSError as exc:
            return self._result(
                command,
                started,
                monotonic_start,
                "error",
                None,
                stderr=str(exc).encode(),
            )
        status = "passed" if completed.returncode == 0 else "failed"
        return self._result(
            command,
            started,
            monotonic_start,
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )
