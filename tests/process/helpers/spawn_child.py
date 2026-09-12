"""Deterministic child-process fixture for ProcessSupervisor tests."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path


def _ignore_term() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--ignore-term", action="store_true")
    parser.add_argument("--grandchild", action="store_true")
    parser.add_argument("--pid-file", default="")
    parser.add_argument("--output-bytes", type=int, default=0)
    parser.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    parser.add_argument("--echo-arg", default="")
    args = parser.parse_args(argv)
    if args.ignore_term:
        _ignore_term()
    pids = [str(os.getpid())]
    child_pid = 0
    if args.grandchild:
        child_pid = os.fork()
        if child_pid == 0:
            if args.ignore_term:
                _ignore_term()
            if args.sleep > 0:
                time.sleep(args.sleep)
            return 0
        pids.append(str(child_pid))
    if args.pid_file:
        Path(args.pid_file).write_text("\n".join(pids) + "\n", encoding="utf-8")
    if args.echo_arg:
        print(args.echo_arg, flush=True)
    if args.output_bytes:
        target = sys.stdout.buffer if args.stream == "stdout" else sys.stderr.buffer
        chunk = b"x" * 4096
        remaining = args.output_bytes
        while remaining > 0:
            written = min(len(chunk), remaining)
            target.write(chunk[:written])
            remaining -= written
        target.flush()
    if args.sleep > 0:
        time.sleep(args.sleep)
    if child_pid:
        os.waitpid(child_pid, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
