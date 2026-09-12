"""Offline evaluation CLI. Does not assemble a real provider runtime."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from vera.evals.codec import EvalCodecError
from vera.evals.corpus import CorpusError, CorpusLoader

eval_app = typer.Typer(help="Run bundled offline Vera evaluations")


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(5)


def _loader() -> CorpusLoader:
    return CorpusLoader()


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
