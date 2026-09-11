import os
import sys

import pytest

from tests.pty.harness import PtyHarness
from vera.terminal.mode import TerminalCapabilities, TerminalModeError, select_mode


def test_pty_harness_runs_trivial_process() -> None:
    result = PtyHarness().spawn_and_run(
        [sys.executable, "-c", "print('vera-pty-ok')"],
        env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
        timeout=5.0,
    )
    assert result.exit_code == 0
    assert "vera-pty-ok" in result.output


def test_dumb_term_requires_explicit_mode() -> None:
    caps = TerminalCapabilities(stdin_tty=True, stdout_tty=True, term="dumb", columns=80, rows=24)
    with pytest.raises(TerminalModeError):
        select_mode(False, False, caps)


def test_supported_tty_defaults_to_tui() -> None:
    caps = TerminalCapabilities(
        stdin_tty=True, stdout_tty=True, term="xterm-256color", columns=80, rows=24
    )
    assert select_mode(False, False, caps).value == "tui"
