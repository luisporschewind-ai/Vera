from __future__ import annotations

import os
import sys

from tests.pty.harness import PtyHarness


def test_phase8_pty_plain_git_boundary_has_text_without_ansi() -> None:
    script = (
        "from vera.cli_presenter import HumanPresenter; "
        "from vera.contracts.events import EventEnvelope; "
        "from datetime import datetime, UTC; "
        "e=EventEnvelope(event_id='e',run_id='r',sequence=1,timestamp=datetime.now(UTC),"
        "type='git.operation.manual_required',payload={'error_code':'manual_required'}); "
        "HumanPresenter(print).write_events((e,))"
    )
    env = os.environ.copy()
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"
    result = PtyHarness().spawn_and_run([sys.executable, "-c", script], env=env)

    assert result.exit_code == 0
    assert "Git 操作需要人工处理：manual_required" in result.output
    assert "\x1b[" not in result.output
