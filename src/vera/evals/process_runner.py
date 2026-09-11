"""Parent-process worker lifecycle: hard timeout without OS sandbox claims."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from vera.evals.codec import EvalCodec, EvalCodecError
from vera.evals.contracts import EvalWorkerRequest, EvalWorkerResult

_PROVIDER_PREFIXES = (
    "DEEPSEEK_",
    "GLM_",
    "VERA_LIVE_",
    "VERA_DEEPSEEK_",
    "VERA_GLM_",
    "VERA_PROVIDER_",
    "OPENAI_",
)
_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "TZ",
        "TMPDIR",
        "TMP",
        "TEMP",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONNOUSERSITE",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
    }
)
_TERM_GRACE_SECONDS = 2
_OUTPUT_LIMIT = 64 * 1024
ProcessFactory = Callable[..., Any]


def sanitized_worker_environment(source: Mapping[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        if any(upper.startswith(prefix) for prefix in _PROVIDER_PREFIXES):
            continue
        if key == "VERA_PROVIDER_ENV_FILE" or upper == "VERA_PROVIDER_ENV_FILE":
            continue
        if key in _ALLOWLIST:
            cleaned[key] = value
    return cleaned


class CaseProcessRunner:
    def __init__(self, process_factory: ProcessFactory = subprocess.Popen) -> None:
        self._popen = process_factory

    def run(self, request: EvalWorkerRequest, timeout_seconds: int) -> EvalWorkerResult:
        request.staging_dir.mkdir(parents=True, exist_ok=True)
        request_path = request.staging_dir / "request.json"
        result_path = request.staging_dir / "result.json"
        _write_private(request_path, request.model_dump_json().encode("utf-8"))
        env = sanitized_worker_environment(os.environ)
        argv = [
            sys.executable,
            "-m",
            "vera.evals.worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]
        process = self._popen(
            argv,
            cwd=str(request.workspace),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=_TERM_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=1)
            return EvalWorkerResult(error_code="case_timeout")
        _drain_output(process)
        if result_path.is_file():
            try:
                return EvalCodec.decode_worker_result(
                    result_path.read_bytes(), source="result.json"
                )
            except EvalCodecError:
                return EvalWorkerResult(error_code="worker_protocol_error")
        if getattr(process, "returncode", 0) not in {0, None}:
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


def _drain_output(process: Any) -> None:
    stdout = getattr(process, "stdout", None)
    stderr = getattr(process, "stderr", None)
    if callable(getattr(process, "communicate", None)):
        try:
            process.communicate(timeout=0.1)
            return
        except Exception:
            pass
    for stream in (stdout, stderr):
        if stream is None or isinstance(stream, bytes | str):
            continue
        try:
            stream.read(_OUTPUT_LIMIT)
        except Exception:
            continue
