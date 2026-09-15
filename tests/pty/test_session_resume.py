import os
import sys
from pathlib import Path

from tests.pty.harness import PtyHarness
from vera.cli_options import parse_session_open_request


def test_resume_without_id_does_not_treat_stdin_as_session_id() -> None:
    request = parse_session_open_request(["-r"])
    assert request.mode == "resume_picker"
    assert request.session_id is None
    request = parse_session_open_request(["--json", "-r"])
    assert request.mode == "resume_picker"


def test_pty_json_resume_picker_has_no_ansi(tmp_path: Path) -> None:
    script = tmp_path / "probe.py"
    script.write_text(
        "from vera.cli_options import parse_session_open_request\n"
        "from vera.presentation.sanitize import sanitize_terminal_text\n"
        "req = parse_session_open_request(['--json', '-r'])\n"
        "print('mode=' + req.mode)\n"
        "print('id=' + str(req.session_id))\n"
        "print(sanitize_terminal_text('plain'))\n",
        encoding="utf-8",
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "TERM": "xterm-256color",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
    }
    result = PtyHarness().spawn_and_run(
        [sys.executable, str(script)],
        env=env,
        input_text="should-not-become-session-id\n",
        timeout=5.0,
    )
    assert result.exit_code == 0
    assert "mode=resume_picker" in result.output
    assert "id=None" in result.output
    assert "\x1b[" not in result.output
