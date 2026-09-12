import json
import sys
from pathlib import Path

import pytest

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


def test_runner_does_not_inherit_or_restore_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-should-not-leak")
    monkeypatch.setenv("AUTHORIZATION", "Bearer leak")
    command = VerificationCommand(
        argv=(
            sys.executable,
            "-c",
            "import json, os, sys; json.dump(dict(os.environ), sys.stdout)",
        ),
        cwd=".",
    )
    result = VerificationRunner(
        tmp_path,
        allowed_environment=("DEEPSEEK_API_KEY", "GITHUB_TOKEN", "AUTHORIZATION"),
    ).run(command)
    env = json.loads(result.stdout)
    assert "sk-should-not-leak" not in result.stdout
    assert "ghp-should-not-leak" not in result.stdout
    assert "Bearer leak" not in result.stdout
    assert "DEEPSEEK_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "AUTHORIZATION" not in env


def test_runner_times_out_and_reaps_child(tmp_path: Path) -> None:
    helper = Path(__file__).resolve().parents[1] / "process" / "helpers" / "spawn_child.py"
    result = VerificationRunner(tmp_path, max_output_bytes=64).run(
        VerificationCommand(
            argv=(sys.executable, str(helper), "--sleep", "30"),
            cwd=".",
            timeout_seconds=1,
        )
    )
    assert result.status == "timed_out"
    assert result.exit_code is None
