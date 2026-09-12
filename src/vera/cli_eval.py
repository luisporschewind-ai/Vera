"""Offline evaluation CLI. Does not assemble a real provider runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer
from platformdirs import user_state_path

from vera.evals.codec import EvalCodec, EvalCodecError
from vera.evals.contracts import EvalReport, EvalStatus, EvalSuiteReport
from vera.evals.corpus import CorpusError, CorpusLoader
from vera.evals.dogfood import DogfoodError, load_dogfood_log, summarize_dogfood
from vera.evals.evidence import EvidenceError
from vera.evals.runner import EvalSuiteRunner

eval_app = typer.Typer(help="Run bundled offline Vera evaluations")


def _emit_json(payload: dict[str, Any] | str) -> None:
    if isinstance(payload, str):
        typer.echo(payload)
        return
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(5)


def _loader() -> CorpusLoader:
    return CorpusLoader()


def _output_parent(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return Path(user_state_path("Vera")) / "evals"


def _status_exit(status: EvalStatus) -> int:
    if status is EvalStatus.PASS:
        return 0
    if status in {EvalStatus.FAIL, EvalStatus.TIMEOUT}:
        return 4
    return 5


def _suite_exit(report: EvalSuiteReport) -> int:
    if report.status is EvalStatus.PASS:
        return 0
    if any(item.status in {EvalStatus.FAIL, EvalStatus.TIMEOUT} for item in report.cases):
        return 4
    return 5


def _print_report(report: EvalReport, evidence: Path | None) -> None:
    typer.echo(f"{report.case_id}\t{report.status.value}")
    for score in report.scores:
        codes = ",".join(score.reason_codes)
        typer.echo(f"{score.dimension.value}\t{score.status.value}\t{codes}")
    wall = report.metrics.wall_duration_seconds
    typer.echo("wall\tnull" if wall is None else f"wall\t{wall}")
    usage = report.metrics.usage
    if usage is None:
        typer.echo("usage\tnull")
    else:
        typer.echo(f"usage\t{usage.total_tokens}")
    if evidence is not None:
        typer.echo(f"evidence\t{evidence}")


@eval_app.command("validate")
def eval_validate(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        validation = _loader().validate()
    except (CorpusError, EvalCodecError, OSError, ValueError) as exc:
        _fail(str(exc))
    payload = {
        "schema_version": 1,
        "manifest_hash": validation.manifest_hash,
        "case_ids": list(validation.case_ids),
        "file_count": validation.file_count,
    }
    if json_output:
        _emit_json(payload)
        return
    typer.echo(f"valid\t{len(validation.case_ids)}\t{validation.manifest_hash}")
    for case_id in validation.case_ids:
        typer.echo(case_id)


@eval_app.command("list")
def eval_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        cases = _loader().list_cases()
    except (CorpusError, EvalCodecError, OSError, ValueError) as exc:
        _fail(str(exc))
    payload = {
        "schema_version": 1,
        "cases": [
            {
                "case_id": case.case_id,
                "title": case.title,
                "tags": [tag.value for tag in case.tags],
                "timeout_seconds": case.timeout_seconds,
                "scenario": case.scenario.value,
            }
            for case in cases
        ],
    }
    if json_output:
        _emit_json(payload)
        return
    for case in cases:
        tags = ",".join(tag.value for tag in case.tags)
        typer.echo(f"{case.case_id}\t{tags}\t{case.timeout_seconds}")


@eval_app.command("run")
def eval_run(
    case_id: Annotated[str | None, typer.Argument()] = None,
    suite: Annotated[str | None, typer.Option("--suite")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    if (case_id is None) == (suite is None):
        _fail("specify either a case id or --suite offline")
    if suite is not None and suite != "offline":
        _fail("unsupported evaluation suite")
    parent = _output_parent(output)
    runner = EvalSuiteRunner()
    try:
        if case_id is not None:
            report = runner.run_case(case_id, parent)
            if json_output:
                _emit_json(EvalCodec.encode_report(report))
            else:
                _print_report(report, parent / report.evaluation_id)
            raise typer.Exit(_status_exit(report.status))
        case_ids = tuple(case.case_id for case in _loader().list_cases())
        suite_root = parent / f"suite-{uuid4().hex}"
        suite_report = runner.run_suite(case_ids, suite_root)
        if json_output:
            _emit_json(EvalCodec.encode_suite_report(suite_report))
        else:
            for item in suite_report.cases:
                _print_report(item, suite_root / item.evaluation_id)
            typer.echo(f"suite\t{suite_report.status.value}\t{suite_root}")
        raise typer.Exit(_suite_exit(suite_report))
    except KeyboardInterrupt as exc:
        raise typer.Exit(2) from exc
    except typer.Exit:
        raise
    except (
        CorpusError,
        EvidenceError,
        EvalCodecError,
        OSError,
        ValueError,
        FileExistsError,
    ) as exc:
        _fail(str(exc))


@eval_app.command("dogfood-check")
def eval_dogfood_check(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        log = load_dogfood_log(path)
    except DogfoodError as exc:
        _fail(str(exc))
    summary = summarize_dogfood(log)
    if json_output:
        _emit_json(summary)
        return
    typer.echo(f"dogfood\t{summary['count']}\t{summary['user_completed_20']}")
