from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from vera.cli import app
from vera.evals.contracts import (
    DimensionStatus,
    EvalDimension,
    EvalReport,
    EvalScore,
    EvalStatus,
    EvalWorkerRequest,
    EvalWorkerResult,
)
from vera.evals.corpus import CorpusError, CorpusLoader
from vera.evals.evidence import EvidenceError, EvidenceWriter
from vera.evals.process_runner import CaseProcessRunner, sanitized_worker_environment
from vera.evals.runner import EvalSuiteRunner

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "evals" / "valid"


def _copy_valid(tmp_path: Path) -> Path:
    dest = tmp_path / "corpus"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _write_manifest(root: Path) -> None:
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == root / "manifest.json":
            continue
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": files}, indent=2) + "\n",
        encoding="utf-8",
    )


def _timeout_report(case_id: str) -> EvalReport:
    return EvalReport(
        evaluation_id=f"eval-{case_id}",
        case_id=case_id,
        status=EvalStatus.TIMEOUT,
        scores=(
            EvalScore(
                dimension=EvalDimension.CORRECTNESS,
                status=DimensionStatus.FAIL,
                reason_codes=("case_timeout",),
            ),
        ),
        reason_codes=("case_timeout",),
    )


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr("vera.cli_eval.user_state_path", lambda _name: state)
    return state


@pytest.fixture
def eval_runner_with_timeout(eval_runner: EvalSuiteRunner) -> EvalSuiteRunner:
    def run(case_id: str, output_root: Path | None = None) -> EvalReport:
        if case_id == "hang":
            return _timeout_report("hang")
        return eval_runner.run_case(case_id, output_root)

    return EvalSuiteRunner(case_runner=run)


def test_timeout_case_does_not_block_following_case(
    eval_runner_with_timeout: EvalSuiteRunner,
) -> None:
    report = eval_runner_with_timeout.run_suite(("hang", "plain-answer"))
    assert report.case("hang").reason_codes == ("case_timeout",)
    assert report.case("hang").status is EvalStatus.TIMEOUT
    assert report.case("plain-answer").status is EvalStatus.PASS
    assert report.status is EvalStatus.FAIL


def test_eval_never_reads_provider_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner
) -> None:
    provider_file = tmp_path / "must-not-read.env"
    provider_file.write_text("DEEPSEEK_API_KEY=sentinel-secret\n", encoding="utf-8")
    provider_file.chmod(0)
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(provider_file))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sentinel-secret")
    monkeypatch.setattr("vera.cli_eval.user_state_path", lambda _name: tmp_path / "state")
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 0
    assert "sentinel-secret" not in result.stdout
    assert "sentinel-secret" not in (result.stderr or "")
    env = sanitized_worker_environment(
        {
            "PATH": "/bin",
            "DEEPSEEK_API_KEY": "sentinel-secret",
            "VERA_PROVIDER_ENV_FILE": str(provider_file),
        }
    )
    assert "DEEPSEEK_API_KEY" not in env
    assert "VERA_PROVIDER_ENV_FILE" not in env


def test_loader_rejects_symlink_fifo_and_manifest_mismatch(tmp_path: Path) -> None:
    corpus = _copy_valid(tmp_path)
    link = corpus / "plain-answer" / "workspace" / "link.md"
    link.symlink_to(corpus / "plain-answer" / "workspace" / "README.md")
    _write_manifest(corpus)
    with pytest.raises(CorpusError, match="special_file"):
        CorpusLoader(corpus).validate()

    fifo_root = _copy_valid(tmp_path / "fifo")
    os.mkfifo(fifo_root / "plain-answer" / "workspace" / "pipe")
    with pytest.raises(CorpusError, match="special_file"):
        CorpusLoader(fifo_root).validate()

    mismatched = _copy_valid(tmp_path / "mismatch")
    (mismatched / "plain-answer" / "workspace" / "README.md").write_text(
        "changed\n", encoding="utf-8"
    )
    with pytest.raises(CorpusError, match="manifest_mismatch"):
        CorpusLoader(mismatched).validate()


def test_loader_rejects_path_escape_in_manifest(tmp_path: Path) -> None:
    corpus = _copy_valid(tmp_path)
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [{"path": "../outside.txt", "sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="illegal_path"):
        CorpusLoader(corpus).validate()


def test_existing_output_and_missing_report_are_closed(
    tmp_path: Path, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vera.evals.runner.uuid4", lambda: SimpleNamespace(hex="fixedid"))
    output = tmp_path / "out"
    first = cli_runner.invoke(
        app, ["eval", "run", "plain-answer", "--json", "--output", str(output)]
    )
    assert first.exit_code == 0
    second = cli_runner.invoke(
        app, ["eval", "run", "plain-answer", "--json", "--output", str(output)]
    )
    assert second.exit_code == 5

    with pytest.raises(EvidenceError, match="missing_report"):
        EvidenceWriter().publish(
            EvalWorkerResult(error_code="worker_protocol_error"),
            tmp_path / "evidence",
        )


def test_incomplete_worker_result_is_protocol_error(tmp_path: Path) -> None:
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

    class EmptyProcess:
        pid = 9
        returncode = 0
        stdout = b""
        stderr = b""

        def __call__(self, *_args: object, **_kwargs: object) -> EmptyProcess:
            return self

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            del timeout
            return self.stdout, self.stderr

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    result = CaseProcessRunner(process_factory=EmptyProcess()).run(request, 5)
    assert result.error_code == "worker_protocol_error"
    assert result.report is None


def test_huge_stderr_is_drained_without_being_copied(tmp_path: Path) -> None:
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
    reads: list[int] = []

    class LimitedStream:
        def __init__(self) -> None:
            self.remaining = 200_000

        def read(self, size: int = -1) -> bytes:
            reads.append(size)
            if self.remaining <= 0:
                return b""
            n = min(max(size, 0), self.remaining)
            self.remaining -= n
            return b"x" * n

    class HugeProcess:
        pid = 11
        returncode = 1
        stdout = LimitedStream()
        stderr = LimitedStream()

        def __call__(self, *_args: object, **_kwargs: object) -> HugeProcess:
            return self

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 1

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            del timeout
            raise RuntimeError("force stream drain")

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    result = CaseProcessRunner(process_factory=HugeProcess()).run(request, 5)
    assert result.error_code == "worker_exit_error"
    assert reads
    assert all(size <= 8192 for size in reads)
    assert result.report is None


def test_timeout_sends_term_then_kill(tmp_path: Path) -> None:
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
            raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout or 0)

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            del timeout
            return self.stdout, self.stderr

    fake = FakeProcess()
    result = CaseProcessRunner(process_factory=fake).run(request, 1)
    assert result.error_code == "case_timeout"
    assert fake.terminated and fake.killed


def test_source_corpus_hash_is_stable_and_evidence_omits_workspace_body(
    eval_runner: EvalSuiteRunner, corpus_loader: CorpusLoader, tmp_path: Path
) -> None:
    before = corpus_loader.validate().manifest_hash
    output = tmp_path / "evidence"
    report = eval_runner.run_case("plain-answer", output)
    assert report.status is EvalStatus.PASS
    assert corpus_loader.validate().manifest_hash == before
    published = output / report.evaluation_id
    files_text = (published / "files.json").read_text(encoding="utf-8")
    report_text = (published / "report.json").read_text(encoding="utf-8")
    assert "fixture" not in files_text
    assert '"content"' not in files_text
    assert "This repository is a fixture." not in files_text
    assert "This repository is a fixture." not in report_text
