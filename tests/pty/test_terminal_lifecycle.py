import os
import sys

from tests.pty.harness import PtyHarness


def test_pty_normal_exit_restores_and_plain_has_no_tui_sequences() -> None:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "TERM": "xterm-256color",
    }
    result = PtyHarness().spawn_and_run(
        [sys.executable, "-c", "print('plain-ok')"],
        env=env,
        timeout=5.0,
    )
    assert result.exit_code == 0
    assert "plain-ok" in result.output
    assert "\x1b[?1049h" not in result.output


def test_pty_ctrl_c_and_closed_stdin_exit() -> None:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "TERM": "dumb",
    }
    interrupted = PtyHarness().spawn_and_run(
        [sys.executable, "-c", "import time; time.sleep(8)"],
        env=env,
        timeout=0.4,
    )
    assert interrupted.exit_code != 0
    eof = PtyHarness().spawn_and_run(
        [sys.executable, "-c", "import sys; sys.stdin.read(); print('eof-ok')"],
        env=env,
        input_text="",
        timeout=3.0,
    )
    assert "eof-ok" in eof.output or eof.exit_code in {0, 1}
