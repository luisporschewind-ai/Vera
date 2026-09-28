"""Supervise child processes with process groups and bounded output."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

ProcessFactory = Callable[..., Any]
ProcessStatus = Literal["exited", "timed_out", "cancelled", "error"]
_TERM_GRACE_SECONDS = 2
_POLL_SECONDS = 0.05
_JOIN_SECONDS = 2.0
_READ_CHUNK = 8192


@dataclass(frozen=True)
class ProcessRequest:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    timeout_seconds: float
    max_output_bytes: int = 100_000
    apple_ios_build_services: bool = False
    effective_argv: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ProcessResult:
    status: ProcessStatus
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    group_managed: bool = False
    cleanup_error: str | None = None
    effective_argv: tuple[str, ...] | None = None


class ProcessAdapter(Protocol):
    def spawn_kwargs(self) -> dict[str, Any]: ...

    def terminate_group(self, process: Any) -> None: ...

    def kill_group(self, process: Any) -> None: ...

    def manages_group(self) -> bool: ...


class PosixProcessAdapter:
    def spawn_kwargs(self) -> dict[str, Any]:
        return {"start_new_session": True}

    def terminate_group(self, process: Any) -> None:
        _signal_group(process, signal.SIGTERM, "terminate")

    def kill_group(self, process: Any) -> None:
        _signal_group(process, signal.SIGKILL, "kill")

    def manages_group(self) -> bool:
        return True


class FallbackProcessAdapter:
    def spawn_kwargs(self) -> dict[str, Any]:
        return {}

    def terminate_group(self, process: Any) -> None:
        _call_if_present(process, "terminate")

    def kill_group(self, process: Any) -> None:
        _call_if_present(process, "kill")

    def manages_group(self) -> bool:
        return False


def default_process_adapter() -> ProcessAdapter:
    if os.name == "posix":
        return PosixProcessAdapter()
    return FallbackProcessAdapter()


class ProcessSupervisor:
    def __init__(
        self,
        process_factory: ProcessFactory = subprocess.Popen,
        adapter: ProcessAdapter | None = None,
        *,
        term_grace_seconds: float = _TERM_GRACE_SECONDS,
        strict_group: bool = False,
    ) -> None:
        self._popen = process_factory
        self._adapter = adapter or default_process_adapter()
        self._term_grace_seconds = term_grace_seconds
        self._strict_group = strict_group

    def run(
        self,
        request: ProcessRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> ProcessResult:
        if not request.argv or any("\x00" in part for part in request.argv):
            return ProcessResult(
                status="error",
                exit_code=None,
                stdout=b"",
                stderr=b"invalid argv",
                group_managed=self._adapter.manages_group(),
            )
        try:
            process = self._popen(
                list(request.argv),
                cwd=str(request.cwd),
                env=dict(request.env),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                shell=False,
                **self._adapter.spawn_kwargs(),
            )
        except TypeError:
            if self._strict_group:
                return ProcessResult("error", None, b"", b"process_group_unavailable")
            process = self._popen(
                list(request.argv),
                cwd=str(request.cwd),
                env=dict(request.env),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except OSError as exc:
            return ProcessResult(
                status="error",
                exit_code=None,
                stdout=b"",
                stderr=str(exc).encode(),
                group_managed=self._adapter.manages_group(),
            )
        collectors = _OutputCollectors(process, request.max_output_bytes)
        collectors.start()
        status: ProcessStatus = "exited"
        try:
            status = self._wait(process, request.timeout_seconds, cancel_event)
        except BaseException:
            # A terminal interrupt must not leave the supervised command alive.
            self._reap(process)
            raise
        finally:
            if self._strict_group:
                self._adapter.kill_group(process)
            stdout, stderr, stdout_truncated, stderr_truncated = collectors.finish()
        return ProcessResult(
            status=status,
            exit_code=getattr(process, "returncode", None),
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            group_managed=self._adapter.manages_group(),
        )

    def _wait(
        self,
        process: Any,
        timeout_seconds: float,
        cancel_event: threading.Event | None,
    ) -> ProcessStatus:
        if cancel_event is None:
            try:
                process.wait(timeout=max(0.0, timeout_seconds))
                return "exited"
            except subprocess.TimeoutExpired:
                self._reap(process)
                return "timed_out"
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            if cancel_event.is_set():
                self._reap(process)
                return "cancelled"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._reap(process)
                return "timed_out"
            try:
                process.wait(timeout=min(_POLL_SECONDS, remaining))
                return "exited"
            except subprocess.TimeoutExpired:
                continue

    def _reap(self, process: Any) -> None:
        self._adapter.terminate_group(process)
        try:
            process.wait(timeout=self._term_grace_seconds)
            if self._strict_group:
                self._adapter.kill_group(process)
            return
        except subprocess.TimeoutExpired:
            pass
        self._adapter.kill_group(process)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=1)


class _BoundedBuffer:
    def __init__(self, limit: int, initial: bytes = b"") -> None:
        self._limit = max(0, limit)
        self._data = bytearray()
        self.truncated = False
        if initial:
            self.extend(initial)

    def extend(self, chunk: bytes) -> None:
        if not chunk:
            return
        if self.truncated:
            return
        remaining = self._limit - len(self._data)
        if remaining <= 0:
            self.truncated = True
            return
        if len(chunk) > remaining:
            self._data.extend(chunk[:remaining])
            self.truncated = True
            return
        self._data.extend(chunk)

    def getvalue(self) -> bytes:
        return bytes(self._data)


class _OutputCollectors:
    def __init__(self, process: Any, limit: int) -> None:
        self._stop = threading.Event()
        self._stdout = _BoundedBuffer(limit, _precollected(getattr(process, "stdout", None)))
        self._stderr = _BoundedBuffer(limit, _precollected(getattr(process, "stderr", None)))
        self._threads: list[threading.Thread] = []
        stdout = getattr(process, "stdout", None)
        stderr = getattr(process, "stderr", None)
        if _is_stream(stdout):
            self._threads.append(
                threading.Thread(target=self._pump, args=(stdout, self._stdout), daemon=True)
            )
        if _is_stream(stderr):
            self._threads.append(
                threading.Thread(target=self._pump, args=(stderr, self._stderr), daemon=True)
            )

    def start(self) -> None:
        for thread in self._threads:
            thread.start()

    def finish(self) -> tuple[bytes, bytes, bool, bool]:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=_JOIN_SECONDS)
        return (
            self._stdout.getvalue(),
            self._stderr.getvalue(),
            self._stdout.truncated,
            self._stderr.truncated,
        )

    def _pump(self, stream: Any, buffer: _BoundedBuffer) -> None:
        while not self._stop.is_set():
            try:
                chunk = stream.read(_READ_CHUNK)
            except Exception:
                break
            if not chunk:
                break
            if isinstance(chunk, str):
                chunk = chunk.encode()
            buffer.extend(chunk)


def _precollected(stream: Any) -> bytes:
    if isinstance(stream, bytes):
        return stream
    if isinstance(stream, str):
        return stream.encode()
    return b""


def _is_stream(stream: Any) -> bool:
    return (
        stream is not None
        and not isinstance(stream, bytes | str)
        and callable(getattr(stream, "read", None))
    )


def _signal_group(process: Any, sig: int, method_name: str) -> None:
    if isinstance(process, subprocess.Popen) and process.pid:
        with suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(process.pid, sig)
            return
    _call_if_present(process, method_name)


def _call_if_present(process: Any, method_name: str) -> None:
    method = getattr(process, method_name, None)
    if callable(method):
        with suppress(Exception):
            method()
