"""Parent-process worker lifecycle: hard timeout without OS sandbox claims."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from vera.evals.codec import EvalCodec, EvalCodecError
from vera.evals.contracts import EvalWorkerRequest, EvalWorkerResult
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessSupervisor

_TERM_GRACE_SECONDS = 2
_OUTPUT_LIMIT = 64 * 1024
ProcessFactory = Callable[..., Any]


def sanitized_worker_environment(source: Mapping[str, str]) -> dict[str, str]:
    return dict(build_child_environment({}, purpose="eval_worker", source=source).values)


class CaseProcessRunner:
    def __init__(
        self,
        process_factory: ProcessFactory = subprocess.Popen,
        supervisor: ProcessSupervisor | None = None,
    ) -> None:
        self._supervisor = supervisor or ProcessSupervisor(
            process_factory=process_factory,
            term_grace_seconds=_TERM_GRACE_SECONDS,
        )

    def run(self, request: EvalWorkerRequest, timeout_seconds: int) -> EvalWorkerResult:
        request.staging_dir.mkdir(parents=True, exist_ok=True)
        request_path = request.staging_dir / "request.json"
        result_path = request.staging_dir / "result.json"
        _write_private(request_path, request.model_dump_json().encode("utf-8"))
        env = sanitized_worker_environment(os.environ)
        argv = (
            sys.executable,
            "-m",
            "vera.evals.worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        )
        completed = self._supervisor.run(
            ProcessRequest(
                argv=argv,
                cwd=request.workspace,
                env=env,
                timeout_seconds=timeout_seconds,
                max_output_bytes=_OUTPUT_LIMIT,
            )
        )
        if completed.status in {"timed_out", "cancelled"}:
            return EvalWorkerResult(error_code="case_timeout")
        if result_path.is_file():
            try:
                return EvalCodec.decode_worker_result(
                    result_path.read_bytes(), source="result.json"
                )
            except EvalCodecError:
                return EvalWorkerResult(error_code="worker_protocol_error")
        if completed.exit_code not in {0, None}:
            return EvalWorkerResult(error_code="worker_exit_error")
        return EvalWorkerResult(error_code="worker_protocol_error")


def _write_private(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
