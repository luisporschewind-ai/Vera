from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vera.cli import app
from vera.evals.corpus import CorpusError, CorpusLoader


def forbidden_call(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("provider loader must not be called")


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


def test_eval_list_needs_no_provider(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vera.bootstrap.build_runtime", forbidden_call)
    monkeypatch.setattr("vera.config.load_provider_environment", forbidden_call)
    monkeypatch.setattr("vera.cli.build_runtime", forbidden_call)
    result = cli_runner.invoke(app, ["eval", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    ids = [item["case_id"] for item in payload["cases"]]
    assert ids == sorted(ids)
    assert len(payload["cases"]) == 14
    assert "\x1b" not in result.stdout
    assert "Vera >" not in result.stdout


def test_eval_validate_json_reports_manifest_hash(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "validate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    expected = CorpusLoader().validate()
    assert payload["manifest_hash"] == expected.manifest_hash
    assert payload["case_ids"] == list(expected.case_ids)
    assert payload["file_count"] == expected.file_count


def test_eval_validate_human_has_no_ansi(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "validate"])
    assert result.exit_code == 0
    assert result.stdout.startswith("valid\t")
    assert "\x1b" not in result.stdout


def test_eval_validate_corrupt_corpus_exits_5(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenLoader:
        def validate(self) -> None:
            raise CorpusError("invalid_contract", "case.json", "broken")

    monkeypatch.setattr("vera.cli_eval.CorpusLoader", BrokenLoader)
    result = cli_runner.invoke(app, ["eval", "validate", "--json"])
    assert result.exit_code == 5
    assert result.stdout == "" or "broken" not in result.stdout


def test_eval_unknown_option_is_rejected(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "list", "--live"])
    assert result.exit_code != 0


def test_eval_list_from_non_repo_cwd(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(app, ["eval", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["cases"]) == 14
