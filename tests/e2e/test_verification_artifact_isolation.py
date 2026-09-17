from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vera.contracts.verification import VerificationCommand
from vera.process.supervisor import ProcessRequest, ProcessResult
from vera.verification.artifacts import VerificationArtifactPlanner
from vera.verification.runner import VerificationRunner, git_porcelain, workspace_file_fingerprint


class RecordingSupervisor:
    def __init__(self) -> None:
        self.requests: list[ProcessRequest] = []

    def run(self, request: ProcessRequest, *, cancel_event=None) -> ProcessResult:
        del cancel_event
        self.requests.append(request)
        return ProcessResult(status="exited", exit_code=0, stdout=b"", stderr=b"")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "hello.txt").write_text("old\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "vera-tests@example.invalid")
    _git(repo, "config", "user.name", "Vera Tests")
    _git(repo, "add", "hello.txt")
    _git(repo, "commit", "-qm", "fixture")
    return repo


@pytest.mark.parametrize(
    "argv",
    [
        ("xcodebuild", "-project", "Demo.xcodeproj", "-scheme", "Demo", "build"),
        ("swift", "test"),
        ("pytest", "-q"),
    ],
)
def test_fake_profiles_do_not_change_workspace_or_git(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    workspace = _repo(tmp_path)
    prefix = tmp_path / "vera-verification"
    planned = VerificationArtifactPlanner(prefix=prefix).plan(
        VerificationCommand(argv=argv),
        workspace_root=workspace,
        installation_id="e2e",
        run_id="run_iso",
        index=0,
    )
    before_files = workspace_file_fingerprint(workspace)
    before_git = git_porcelain(workspace)
    supervisor = RecordingSupervisor()
    result = VerificationRunner(
        workspace,
        supervisor=supervisor,
        artifact_prefix=prefix,
    ).run(planned)
    assert result.status == "passed"
    assert supervisor.requests
    assert workspace_file_fingerprint(workspace) == before_files
    assert git_porcelain(workspace) == before_git
    assert not (workspace / "build").exists()
    assert not (workspace / ".build").exists()
    assert not (workspace / ".pytest_cache").exists()
    assert planned.artifact_plan is not None
    assert not Path(planned.artifact_plan.root).exists()


@pytest.mark.skipif(shutil.which("xcodebuild") is None, reason="xcodebuild is not available")
def test_real_xcodebuild_writes_outside_workspace(tmp_path: Path) -> None:
    workspace = _repo(tmp_path)
    (workspace / "Demo").mkdir()
    (workspace / "Demo" / "main.swift").write_text('print("hi")\n', encoding="utf-8")
    # A missing xcodeproj will fail the tool, but must still not create workspace build/.
    planned = VerificationArtifactPlanner().plan(
        VerificationCommand(
            argv=("xcodebuild", "-project", "Demo.xcodeproj", "-scheme", "Demo", "build")
        ),
        workspace_root=workspace,
        installation_id="e2e-real",
        run_id="run_xcode",
        index=0,
    )
    assert planned.artifact_plan is not None
    assert str(planned.artifact_plan.root).startswith("/private/tmp/vera-verification/")
    result = VerificationRunner(workspace).run(planned)
    assert result.status in {"failed", "error", "passed", "timed_out"}
    assert not (workspace / "build").exists()
    assert result.reason_code != "workspace_polluted"
