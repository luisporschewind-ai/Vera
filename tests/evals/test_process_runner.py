from __future__ import annotations

import subprocess
from pathlib import Path

from vera.evals.contracts import EvalWorkerRequest
from vera.evals.process_runner import CaseProcessRunner, sanitized_worker_environment


def test_worker_environment_removes_all_provider_values() -> None:
    source = {
        "PATH": "/bin",
        "DEEPSEEK_API_KEY": "secret",
        "GLM_API_KEY": "secret-2",
        "VERA_LIVE_API_KEY": "secret-3",
    }
    result = sanitized_worker_environment(source)
    assert result == {"PATH": "/bin"}


def test_timeout_terminates_exact_worker_and_returns_timeout(tmp_path: Path) -> None:
    request = EvalWorkerRequest(
        evaluation_id="eval-1",
        case_id="plain-answer",
        corpus_root=tmp_path / "corpus",
        workspace=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        staging_dir=tmp_path / "staging",
    )
    request.workspace.mkdir()
    request.state_dir.mkdir()
    request.staging_dir.mkdir()

    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.waited_after_term = 0
            self.pid = 4242
            self.returncode = None
            self.stdout = b""
            self.stderr = b""

        def __call__(self, *_args: object, **_kwargs: object) -> FakeProcess:
            return self

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            if self.killed:
                return 9
            if not self.terminated:
                raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout or 0)
            self.waited_after_term = int(timeout or 0)
            raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout or 0)

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            del timeout
            return self.stdout, self.stderr

    fake_process = FakeProcess()
    result = CaseProcessRunner(process_factory=fake_process).run(request, 1)
    assert result.error_code == "case_timeout"
    assert fake_process.terminated and fake_process.waited_after_term == 2
    assert fake_process.killed


def test_nonzero_exit_without_result_is_protocol_or_exit_error(tmp_path: Path) -> None:
    request = EvalWorkerRequest(
        evaluation_id="eval-1",
        case_id="plain-answer",
        corpus_root=tmp_path / "corpus",
        workspace=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        staging_dir=tmp_path / "staging",
    )
    request.workspace.mkdir()
    request.state_dir.mkdir()
    request.staging_dir.mkdir()

    class ExitingProcess:
        pid = 7
        returncode = 1
        stdout = b""
        stderr = b"boom"

        def __call__(self, *_args: object, **_kwargs: object) -> ExitingProcess:
            return self

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 1

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            del timeout
            return self.stdout, self.stderr

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    result = CaseProcessRunner(process_factory=ExitingProcess()).run(request, 5)
    assert result.error_code in {"worker_exit_error", "worker_protocol_error"}
