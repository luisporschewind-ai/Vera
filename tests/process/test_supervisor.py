from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessSupervisor

HELPER = Path(__file__).resolve().parent / "helpers" / "spawn_child.py"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _env() -> dict[str, str]:
    return dict(build_child_environment({}, purpose="verification").values)


def _request(
    tmp_path: Path,
    *args: str,
    timeout_seconds: float = 5.0,
    max_output_bytes: int = 1024,
) -> ProcessRequest:
    return ProcessRequest(
        argv=(sys.executable, str(HELPER), *args),
        cwd=tmp_path,
        env=_env(),
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )


def test_timeout_reaps_process_group_including_term_ignorers(tmp_path: Path) -> None:
    pid_file = tmp_path / "pids.txt"
    result = ProcessSupervisor().run(
        _request(
            tmp_path,
            "--grandchild",
            "--ignore-term",
            "--sleep",
            "30",
            "--pid-file",
            str(pid_file),
            timeout_seconds=2.0,
        )
    )
    assert result.status == "timed_out"
    deadline = time.monotonic() + 3
    pids = [int(line) for line in pid_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert pids
    while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
        time.sleep(0.05)
    assert all(not _alive(pid) for pid in pids)


def test_cancel_reaps_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "pids.txt"
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    result = ProcessSupervisor().run(
        _request(
            tmp_path,
            "--grandchild",
            "--sleep",
            "30",
            "--pid-file",
            str(pid_file),
            timeout_seconds=10,
        ),
        cancel_event=cancel,
    )
    assert result.status == "cancelled"
    pids = [int(line) for line in pid_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
        time.sleep(0.05)
    assert all(not _alive(pid) for pid in pids)


def test_output_over_limit_is_truncated_and_process_is_reaped(tmp_path: Path) -> None:
    result = ProcessSupervisor().run(
        _request(
            tmp_path,
            "--output-bytes",
            "200000",
            "--sleep",
            "0",
            timeout_seconds=10,
            max_output_bytes=2048,
        )
    )
    assert result.status == "exited"
    assert result.exit_code == 0
    assert result.stdout_truncated is True
    assert len(result.stdout) == 2048


def test_argv_spaces_and_metacharacters_are_literal(tmp_path: Path) -> None:
    payload = "hello world; rm -rf / && echo pwned"
    result = ProcessSupervisor().run(
        _request(tmp_path, "--echo-arg", payload, "--sleep", "0", timeout_seconds=5)
    )
    assert result.status == "exited"
    assert result.stdout.decode("utf-8").strip() == payload
