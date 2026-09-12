from __future__ import annotations

import json
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
    EvalSuiteReport,
)
from vera.evals.corpus import CorpusError
from vera.evals.evidence import EvidenceError
from vera.evals.runner import EvalSuiteRunner


def forbidden_call(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("provider loader must not be called")


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr("vera.cli_eval.user_state_path", lambda _name: state)
    return state


def _report(status: EvalStatus, case_id: str = "plain-answer") -> EvalReport:
    failed = status is not EvalStatus.PASS
    code = "mismatch" if failed else "ok"
    return EvalReport(
        evaluation_id="eval-test",
        case_id=case_id,
        status=status,
        scores=(
            EvalScore(
                dimension=EvalDimension.CORRECTNESS,
                status=DimensionStatus.FAIL if failed else DimensionStatus.PASS,
                reason_codes=(code,),
            ),
        ),
        reason_codes=(code,),
    )


def _decode_one(text: str) -> object:
    payload, index = json.JSONDecoder().raw_decode(text.strip())
    assert text.strip()[index:].strip() == ""
    return payload


def test_eval_suite_json_is_one_document_without_ansi(
    cli_runner: CliRunner, isolated_env: Path
) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "--suite", "offline", "--json"])
    assert result.exit_code == 0
    payload = _decode_one(result.stdout)
    assert isinstance(payload, dict)
    assert payload["schema_version"] == 1
    assert len(payload["cases"]) == 14
    assert payload["status"] == "pass"
    assert "\x1b" not in result.stdout
    assert "Vera >" not in result.stdout


def test_eval_run_rejects_case_and_suite_together(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--suite", "offline"])
    assert result.exit_code == 5


def test_eval_run_requires_case_or_suite(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "run"])
    assert result.exit_code == 5


def test_eval_run_rejects_unknown_suite(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "--suite", "live"])
    assert result.exit_code == 5


def test_eval_run_plain_answer_json_exits_0(
    cli_runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vera.bootstrap.build_runtime", forbidden_call)
    monkeypatch.setattr("vera.config.load_provider_environment", forbidden_call)
    monkeypatch.setattr("vera.config.load_config", forbidden_call)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("GLM_API_KEY", "secret")
    monkeypatch.setenv("VERA_LIVE_API_KEY", "secret")
    output = tmp_path / "out"
    result = cli_runner.invoke(
        app,
        ["eval", "run", "plain-answer", "--json", "--output", str(output)],
    )
    assert result.exit_code == 0
    payload = _decode_one(result.stdout)
    assert isinstance(payload, dict)
    assert payload["case_id"] == "plain-answer"
    assert payload["status"] == "pass"
    assert "\x1b" not in result.stdout
    evidence_dirs = list(output.glob("eval-*"))
    assert len(evidence_dirs) == 1
    assert (evidence_dirs[0] / "report.json").is_file()


def test_eval_run_human_hides_payloads_and_bodies(cli_runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "out"
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--output", str(output)])
    assert result.exit_code == 0
    assert "plain-answer" in result.stdout
    assert "pass" in result.stdout
    assert "evidence" in result.stdout
    assert "This repository is a fixture." not in result.stdout
    assert "fixture" not in result.stdout
    assert "\x1b" not in result.stdout


def test_eval_run_fail_exits_4(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        EvalSuiteRunner,
        "run_case",
        lambda self, case_id, output_root=None: _report(EvalStatus.FAIL),
    )
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 4


def test_eval_run_timeout_exits_4(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        EvalSuiteRunner,
        "run_case",
        lambda self, case_id, output_root=None: _report(EvalStatus.TIMEOUT),
    )
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 4


def test_eval_run_error_exits_5(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        EvalSuiteRunner,
        "run_case",
        lambda self, case_id, output_root=None: _report(EvalStatus.ERROR),
    )
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 5


def test_eval_run_suite_error_exits_5(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = _report(EvalStatus.ERROR)

    def fake_suite(
        self: EvalSuiteRunner, case_ids: object, output_root: Path | None = None
    ) -> EvalSuiteReport:
        return EvalSuiteReport(evaluation_id="suite-x", status=EvalStatus.FAIL, cases=(error,))

    monkeypatch.setattr(EvalSuiteRunner, "run_suite", fake_suite)
    result = cli_runner.invoke(app, ["eval", "run", "--suite", "offline", "--json"])
    assert result.exit_code == 5


def test_eval_run_unknown_case_exits_5(cli_runner: CliRunner, isolated_env: Path) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "missing-case", "--json"])
    assert result.exit_code == 5


def test_eval_run_ctrl_c_exits_2(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: EvalSuiteRunner, case_id: str, output_root: Path | None = None) -> EvalReport:
        raise KeyboardInterrupt

    monkeypatch.setattr(EvalSuiteRunner, "run_case", boom)
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 2


def test_eval_run_output_error_exits_5(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: EvalSuiteRunner, case_id: str, output_root: Path | None = None) -> EvalReport:
        raise EvidenceError(
            "output_exists",
            Path("/tmp/x"),
            "evaluation output directory already exists",
        )

    monkeypatch.setattr(EvalSuiteRunner, "run_case", boom)
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 5


def test_eval_run_corpus_error_exits_5(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: EvalSuiteRunner, case_id: str, output_root: Path | None = None) -> EvalReport:
        raise CorpusError("missing_case", case_id, "unknown case")

    monkeypatch.setattr(EvalSuiteRunner, "run_case", boom)
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 5


def test_eval_run_refuses_existing_output(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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


def test_eval_run_default_output_is_private_state(
    cli_runner: CliRunner, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Path | None] = {}

    def fake_run(
        self: EvalSuiteRunner, case_id: str, output_root: Path | None = None
    ) -> EvalReport:
        captured["root"] = output_root
        return _report(EvalStatus.PASS)

    monkeypatch.setattr(EvalSuiteRunner, "run_case", fake_run)
    monkeypatch.setattr("vera.config.load_config", forbidden_call)
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--json"])
    assert result.exit_code == 0
    assert captured["root"] == isolated_env / "evals"


def test_eval_run_rejects_live_option(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--live"])
    assert result.exit_code != 0
