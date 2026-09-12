from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vera.cli import app
from vera.evals.corpus import CorpusLoader

FROZEN_COUNT = 14


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr("vera.cli_eval.user_state_path", lambda _name: state)
    return state


def _one_json(text: str) -> dict[str, object]:
    payload, index = json.JSONDecoder().raw_decode(text.strip())
    assert text.strip()[index:].strip() == ""
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    ("args", "expect_exit"),
    [
        (["eval", "validate", "--json"], 0),
        (["eval", "list", "--json"], 0),
        (["eval", "run", "plain-answer", "--json"], 0),
        (["eval", "run", "--suite", "offline", "--json"], 0),
    ],
)
def test_phase4_eval_cli_json_is_one_document(
    cli_runner: CliRunner,
    isolated_env: Path,
    args: list[str],
    expect_exit: int,
) -> None:
    result = cli_runner.invoke(app, args)
    assert result.exit_code == expect_exit
    payload = _one_json(result.stdout)
    assert payload["schema_version"] == 1
    assert "\x1b" not in result.stdout
    assert "Vera >" not in result.stdout
    if args[1] == "validate":
        current = CorpusLoader().validate()
        assert payload["manifest_hash"] == current.manifest_hash
        assert payload["case_ids"] == list(current.case_ids)
    elif args[1] == "list":
        assert isinstance(payload["cases"], list)
        assert len(payload["cases"]) == FROZEN_COUNT
    elif "--suite" in args:
        assert payload["status"] == "pass"
        assert isinstance(payload["cases"], list)
        assert len(payload["cases"]) == FROZEN_COUNT
    else:
        assert payload["case_id"] == "plain-answer"
        assert payload["status"] == "pass"


@pytest.mark.parametrize("command", ["validate", "list"])
def test_phase4_eval_cli_human_has_no_ansi(cli_runner: CliRunner, command: str) -> None:
    result = cli_runner.invoke(app, ["eval", command])
    assert result.exit_code == 0
    assert "\x1b" not in result.stdout
    assert "Vera >" not in result.stdout


def test_phase4_eval_run_human_hides_payloads(cli_runner: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    result = cli_runner.invoke(app, ["eval", "run", "plain-answer", "--output", str(output)])
    assert result.exit_code == 0
    assert "plain-answer" in result.stdout
    assert "This repository is a fixture." not in result.stdout
    assert "\x1b" not in result.stdout
    evidence_dirs = list(output.glob("eval-*"))
    assert len(evidence_dirs) == 1


def test_phase4_eval_run_writes_under_explicit_output(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    output = tmp_path / "out"
    result = cli_runner.invoke(
        app, ["eval", "run", "plain-answer", "--json", "--output", str(output)]
    )
    assert result.exit_code == 0
    payload = _one_json(result.stdout)
    evaluation_id = payload["evaluation_id"]
    assert isinstance(evaluation_id, str)
    published = output / evaluation_id
    assert (published / "report.json").is_file()
    assert (published / "files.json").is_file()
    assert (published / "events.jsonl").is_file()


def test_phase4_eval_cli_rejects_live(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["eval", "run", "--suite", "offline", "--live"])
    assert result.exit_code != 0
    assert result.exit_code != 4
