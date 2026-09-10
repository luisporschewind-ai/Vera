"""Human and JSON event CLI for the Vera Core."""

import json
import sys
from pathlib import Path
from typing import Annotated, cast

import typer

from vera.bootstrap import RuntimeDependencies, build_runtime
from vera.cli_driver import ApprovalDecision, drive_run
from vera.config import load_config
from vera.contracts.commands import RollbackRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.persistence.run_store import RunStore

app = typer.Typer(no_args_is_help=True, help="Vera local coding-agent Core")
runs_app = typer.Typer(help="inspect private run records")
config_app = typer.Typer(help="inspect effective configuration")
app.add_typer(runs_app, name="runs")
app.add_typer(config_app, name="config")


def _render(events: list[EventEnvelope], json_output: bool) -> None:
    if json_output:
        for event in events:
            typer.echo(event.model_dump_json())
        return
    for event in events:
        typer.echo(f"{event.type}: {json.dumps(event.payload, ensure_ascii=False)}")


def _exit_code(events: list[EventEnvelope]) -> int:
    if not events:
        return 5
    terminal = events[-1].type
    return {"run.completed": 0, "run.cancelled": 2, "run.failed": 4}.get(terminal, 0)


def execute_run(
    goal: str,
    workspace: Path,
    model_profile: str | None,
    json_output: bool,
    dependencies: RuntimeDependencies | None = None,
) -> int:
    try:
        deps = dependencies or build_runtime(workspace, model_profile)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        return 5
    def decide(_request: EventEnvelope) -> ApprovalDecision:
        if json_output or not sys.stdin.isatty():
            return "cancel"
        decision = typer.prompt("输入 approve 批准，或 reject 拒绝")
        if decision not in {"approve", "reject"}:
            raise typer.BadParameter("必须明确输入 approve 或 reject")
        return cast(ApprovalDecision, decision)

    events = drive_run(
        deps.runtime,
        StartRun(
            goal=goal,
            workspace_root=workspace,
            model_profile=model_profile or "default",
        ),
        decide,
        lambda batch: _render(list(batch), json_output),
    )
    return _exit_code(list(events))


@app.command()
def run(
    goal: str,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    model: Annotated[str | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    raise typer.Exit(execute_run(goal, workspace.resolve(), model, json_output))


@runs_app.command("list")
def list_runs() -> None:
    config = load_config(Path.cwd(), {})
    for summary in RunStore(config.state_dir).list_runs():
        typer.echo(f"{summary.run_id}\t{summary.workspace_root}\t{summary.terminal_state}")


@runs_app.command("show")
def show_run(run_id: str) -> None:
    config = load_config(Path.cwd(), {})
    for event in RunStore(config.state_dir).read_events(run_id):
        typer.echo(event.model_dump_json())


@app.command()
def rollback(run_id: str = typer.Argument(...)) -> None:
    deps = build_runtime(Path.cwd())
    events = list(deps.runtime.handle(RollbackRun(run_id=run_id)))
    _render(events, False)
    raise typer.Exit(_exit_code(events))


@config_app.command("show")
def config_show() -> None:
    config = load_config(Path.cwd(), {})
    typer.echo(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2))
