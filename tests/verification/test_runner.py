import json
import sys
from pathlib import Path

import pytest

from vera.contracts.verification import VerificationArtifactPlan, VerificationCommand
from vera.process.supervisor import ProcessRequest, ProcessResult
from vera.verification.artifacts import (
    VerificationArtifactRoot,
    artifact_root,
    environment_for_plan,
)
from vera.verification.runner import VerificationRunner


class FakeSupervisor:
    def __init__(
        self,
        *,
        status: str = "exited",
        exit_code: int | None = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        side_effect=None,
    ) -> None:
        self.requests: list[ProcessRequest] = []
        self.status = status
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.side_effect = side_effect

    def run(self, request: ProcessRequest, *, cancel_event=None) -> ProcessResult:
        del cancel_event
        self.requests.append(request)
        if self.side_effect is not None:
            self.side_effect(request)
        return ProcessResult(
            status=self.status,  # type: ignore[arg-type]
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _artifact_prefix(tmp_path: Path) -> Path:
    return tmp_path.parent / f"{tmp_path.name}-vera-verification"


def _planned(
    tmp_path: Path,
    argv: tuple[str, ...],
    *,
    cwd: str = ".",
    profile: str = "pytest",
    **kwargs: object,
) -> tuple[VerificationCommand, Path]:
    prefix = _artifact_prefix(tmp_path)
    root = artifact_root(
        workspace_root=tmp_path,
        installation_id="test",
        run_id="run_1",
        index=0,
        prefix=prefix,
    )
    command = VerificationCommand(
        argv=argv,
        cwd=cwd,
        artifact_plan=VerificationArtifactPlan(profile=profile, root=str(root)),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )
    return command, prefix


def test_runner_rejects_unplanned_commands_without_starting(tmp_path: Path) -> None:
    supervisor = FakeSupervisor()
    result = VerificationRunner(tmp_path, supervisor=supervisor).run(
        VerificationCommand(argv=("pytest", "-q"))
    )
    assert result.status == "rejected"
    assert result.reason_code == "verification_not_planned"
    assert supervisor.requests == []


def test_runner_uses_final_argv_cwd_and_planner_environment(tmp_path: Path) -> None:
    command, prefix = _planned(tmp_path, ("pytest", "-q"))
    supervisor = FakeSupervisor(stdout=b"ok")
    result = VerificationRunner(tmp_path, supervisor=supervisor, artifact_prefix=prefix).run(
        command
    )
    assert result.status == "passed"
    assert len(supervisor.requests) == 1
    request = supervisor.requests[0]
    assert request.argv == command.argv
    assert request.cwd == tmp_path
    expected = environment_for_plan(command.artifact_plan)  # type: ignore[arg-type]
    for key, value in expected.items():
        assert request.env[key] == value
    assert "MODEL_INJECTED" not in request.env
    assert result.artifact_cleanup_status == "cleaned"


@pytest.mark.parametrize(
    ("status", "exit_code", "expected"),
    [
        ("exited", 0, "passed"),
        ("exited", 2, "failed"),
        ("timed_out", None, "timed_out"),
        ("cancelled", None, "cancelled"),
        ("error", None, "error"),
    ],
)
def test_runner_always_cleans_exact_root(
    tmp_path: Path, status: str, exit_code: int | None, expected: str
) -> None:
    command, prefix = _planned(tmp_path, ("pytest", "-q"))
    supervisor = FakeSupervisor(status=status, exit_code=exit_code)
    result = VerificationRunner(tmp_path, supervisor=supervisor, artifact_prefix=prefix).run(
        command
    )
    assert result.status == expected
    assert result.artifact_cleanup_status == "cleaned"
    assert not Path(command.artifact_plan.root).exists()  # type: ignore[union-attr]


def test_cleanup_failure_does_not_delete_workspace(tmp_path: Path) -> None:
    command, prefix = _planned(tmp_path, ("pytest", "-q"))
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("evidence", encoding="utf-8")

    class FailingRoots(VerificationArtifactRoot):
        def cleanup(self, root, *, workspace_root):  # type: ignore[no-untyped-def]
            del root, workspace_root
            from vera.verification.artifacts import CleanupResult

            return CleanupResult(status="failed", code="artifact_cleanup_failed")

    result = VerificationRunner(
        tmp_path,
        supervisor=FakeSupervisor(),
        artifact_roots=FailingRoots(prefix=prefix),
    ).run(command)
    assert result.reason_code == "artifact_cleanup_failed"
    assert result.status == "error"
    assert sentinel.read_text(encoding="utf-8") == "evidence"
    assert list(tmp_path.glob("**/.git")) == []


def test_workspace_pollution_is_reported_and_files_are_kept(tmp_path: Path) -> None:
    command, prefix = _planned(tmp_path, ("pytest", "-q"))

    def pollute(request: ProcessRequest) -> None:
        target = Path(request.cwd) / "build" / "sentinel"
        target.parent.mkdir()
        target.write_text("left-behind", encoding="utf-8")

    result = VerificationRunner(
        tmp_path,
        supervisor=FakeSupervisor(side_effect=pollute),
        artifact_prefix=prefix,
    ).run(command)
    assert result.status == "workspace_polluted"
    assert result.reason_code == "workspace_polluted"
    assert result.workspace_mutations == ("build/sentinel",)
    assert (tmp_path / "build" / "sentinel").read_text(encoding="utf-8") == "left-behind"


def test_runner_captures_exit_code_and_truncates_output(tmp_path: Path) -> None:
    command, prefix = _planned(
        tmp_path,
        (sys.executable, "-c", "print('abcdef')"),
        timeout_seconds=5,
    )
    result = VerificationRunner(tmp_path, max_output_bytes=4, artifact_prefix=prefix).run(command)
    assert result.exit_code == 0
    assert result.stdout == "abcd"
    assert result.stdout_truncated is True
    assert result.status == "passed"


def test_runner_captures_failure_stderr_and_rejects_escape(tmp_path: Path) -> None:
    command, prefix = _planned(
        tmp_path,
        (sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(2)"),
    )
    result = VerificationRunner(tmp_path, artifact_prefix=prefix).run(command)
    assert result.exit_code == 2
    assert result.stderr == "bad"
    assert result.status == "failed"
    escaped = VerificationRunner(tmp_path, artifact_prefix=prefix).run(
        command.model_copy(update={"cwd": ".."})
    )
    assert escaped.status == "rejected"


def test_runner_does_not_inherit_or_restore_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-should-not-leak")
    monkeypatch.setenv("AUTHORIZATION", "Bearer leak")
    command, prefix = _planned(
        tmp_path,
        (
            sys.executable,
            "-c",
            "import json, os, sys; json.dump(dict(os.environ), sys.stdout)",
        ),
    )
    result = VerificationRunner(
        tmp_path,
        allowed_environment=("DEEPSEEK_API_KEY", "GITHUB_TOKEN", "AUTHORIZATION"),
        artifact_prefix=prefix,
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
    command, prefix = _planned(
        tmp_path,
        (sys.executable, str(helper), "--sleep", "30"),
        timeout_seconds=1,
    )
    result = VerificationRunner(tmp_path, max_output_bytes=64, artifact_prefix=prefix).run(command)
    assert result.status == "timed_out"
    assert result.exit_code is None
    assert result.artifact_cleanup_status == "cleaned"
