import sys
from pathlib import Path

from vera.contracts.verification import VerificationCommand
from vera.verification.runner import VerificationRunner


def test_runner_captures_exit_code_and_truncates_output(tmp_path: Path) -> None:
    command = VerificationCommand(
        argv=(sys.executable, "-c", "print('abcdef')"), cwd=".", timeout_seconds=5
    )
    result = VerificationRunner(tmp_path, max_output_bytes=4).run(command)
    assert result.exit_code == 0
    assert result.stdout == "abcd"
    assert result.stdout_truncated is True
    assert result.status == "passed"


def test_runner_captures_failure_stderr_and_rejects_escape(tmp_path: Path) -> None:
    command = VerificationCommand(
        argv=(sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(2)"),
        cwd=".",
    )
    result = VerificationRunner(tmp_path).run(command)
    assert result.exit_code == 2
    assert result.stderr == "bad"
    assert result.status == "failed"
    escaped = VerificationRunner(tmp_path).run(
        VerificationCommand(argv=(sys.executable, "-c", "pass"), cwd="..")
    )
    assert escaped.status == "rejected"
