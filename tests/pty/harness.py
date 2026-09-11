"""Minimal PTY helpers for terminal lifecycle checks without live models."""

from __future__ import annotations

import os
import pty
import select
import signal
import time
from contextlib import suppress
from dataclasses import dataclass


@dataclass
class PtyResult:
    output: str
    exit_code: int


class PtyHarness:
    def spawn_and_run(
        self,
        argv: list[str],
        *,
        env: dict[str, str],
        input_text: str = "",
        timeout: float = 5.0,
    ) -> PtyResult:
        pid, master = pty.fork()
        if pid == 0:
            os.environ.clear()
            os.environ.update(env)
            os.execvpe(argv[0], argv, os.environ)
        chunks: list[bytes] = []
        end = time.time() + timeout
        if input_text:
            os.write(master, input_text.encode())
        while time.time() < end:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            else:
                waited = os.waitpid(pid, os.WNOHANG)
                if waited[0] != 0:
                    break
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
        try:
            _, status = os.waitpid(pid, 0)
            code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
        except ChildProcessError:
            code = 1
        with suppress(OSError):
            os.close(master)
        return PtyResult(output=b"".join(chunks).decode("utf-8", errors="replace"), exit_code=code)
