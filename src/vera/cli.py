"""Human and JSON event CLI for the Vera Core."""

import json
import sys
from pathlib import Path
from typing import Annotated, cast

import typer

from vera.bootstrap import RuntimeDependencies, build_runtime
from vera.cli_driver import ApprovalDecision, drive_run
from vera.cli_eval import eval_app
from vera.cli_json_session import JsonSessionDriver
from vera.cli_plain_session import PlainSessionDriver
from vera.cli_presenter import HumanPresenter
from vera.config import load_config
from vera.contracts.commands import (
    AbandonRun,
    ApplyStateMigration,
    InspectRecovery,
    InspectState,
    PlanStateMigration,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope
from vera.persistence.run_store import RunStore
from vera.redaction import Redactor
from vera.terminal.mode import (
    PresentationMode,
    TerminalCapabilities,
    TerminalModeError,
    select_mode,
)

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Vera local coding-agent Core",
)
runs_app = typer.Typer(help="inspect private run records")
config_app = typer.Typer(help="inspect effective configuration")
recover_app = typer.Typer(help="inspect and recover interrupted runs")
state_app = typer.Typer(help="inspect and migrate private run state formats")
app.add_typer(runs_app, name="runs")
app.add_typer(config_app, name="config")
app.add_typer(recover_app, name="recover")
app.add_typer(state_app, name="state")
app.add_typer(eval_app, name="eval")


class _ConsoleSessionIO:
    def read(self, prompt: str) -> str:
        return cast(str, typer.prompt(prompt, prompt_suffix=""))

    def write(self, text: str) -> None:
        typer.echo(text)

    def clear(self) -> None:
        if sys.stdout.isatty():
            typer.echo("\033[2J\033[H", nl=False)


@app.callback()
def main(
    ctx: typer.Context,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    model: Annotated[str | None, typer.Option()] = None,
    plain: Annotated[bool, typer.Option("--plain", help="逐行人类交互模式")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="NDJSON Session 协议")] = False,
) -> None:
    """Start an interactive session when no subcommand is supplied."""

    if ctx.invoked_subcommand is not None:
        return
    resolved = workspace.resolve()
    if not resolved.is_dir():
        typer.echo(f"工作区必须是现有目录：{resolved}")
        raise typer.Exit(2)
    try:
        deps = build_runtime(resolved, model)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(5) from exc
    selected_model = model or next(iter(deps.config.providers), "default")
    capabilities = detect_terminal_capabilities()
    try:
        mode = select_mode(plain=plain, json_output=json_output, capabilities=capabilities)
    except TerminalModeError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(exc.exit_code) from exc
    if mode is PresentationMode.JSON:
        raise typer.Exit(
            JsonSessionDriver(deps, resolved, selected_model).run(sys.stdin, sys.stdout)
        )
    if mode is PresentationMode.PLAIN:
        raise typer.Exit(
            PlainSessionDriver(deps, resolved, selected_model, _ConsoleSessionIO()).run()
        )
    raise typer.Exit(_launch_tui_session(deps, resolved, selected_model))


def detect_terminal_capabilities() -> TerminalCapabilities:
    import os
    import shutil

    size = shutil.get_terminal_size(fallback=(80, 24))
    return TerminalCapabilities(
        stdin_tty=sys.stdin.isatty(),
        stdout_tty=sys.stdout.isatty(),
        term=os.environ.get("TERM", ""),
        columns=size.columns,
        rows=size.lines,
    )


def _launch_tui_session(
    dependencies: RuntimeDependencies,
    workspace: Path,
    model_profile: str,
) -> int:
    from vera.session.controller import SessionController

    try:
        from vera.terminal.app import launch_tui
    except Exception as exc:
        typer.echo(
            f"无法启动 Textual TUI（{exc}）。请改用 --plain。",
            err=True,
        )
        return 2
    controller = SessionController(dependencies, workspace, model_profile)
    try:
        return launch_tui(controller, workspace, model_profile)
    except Exception as exc:
        typer.echo(
            f"TUI 启动失败（{exc}）。请改用 --plain。",
            err=True,
        )
        return 2


def _render(events: list[EventEnvelope], json_output: bool) -> None:
    redactor = Redactor()
    if json_output:
        for event in events:
            typer.echo(redactor.redact_event(event).model_dump_json())
        return
    HumanPresenter(typer.echo, redactor).write_events(events)


def _exit_code(events: list[EventEnvelope]) -> int:
    if not events:
        return 5
    last = events[-1]
    if last.type == "run.completed":
        if last.payload.get("state") == "verification_failed":
            return 3
        return 0
    mapping = {
        "recovery.abandoned": 0,
        "run.cancelled": 2,
        "run.failed": 4,
        "rollback.completed": 0,
        "rollback.conflicted": 4,
        "recovery.manual_required": 5,
    }
    if last.type in mapping:
        return mapping[last.type]
    if last.type == "recovery.detected" and last.payload.get("classification") in {
        "manual_required",
        "legacy_not_resumable",
        "recoverable_partial_apply",
    }:
        return 5
    if last.type == "approval.required" and last.payload.get("kind") == "recovery":
        return 5
    return 0


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
    presenter = HumanPresenter(typer.echo)

    def decide(request: EventEnvelope) -> ApprovalDecision:
        if json_output or not sys.stdin.isatty():
            return "cancel"
        decision = typer.prompt(presenter.approval_prompt(request))
        if decision not in {"approve", "reject", "cancel"}:
            raise typer.BadParameter("必须明确输入 approve、reject 或 cancel")
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
        typer.echo(Redactor().redact_event(event).model_dump_json())


def _inspect_recovery(run_id: str | None, json_output: bool) -> None:
    deps = build_runtime(Path.cwd())
    events = list(deps.runtime.handle(InspectRecovery(run_id=run_id)))
    if json_output:
        _render(events, True)
        raise typer.Exit(0)
    if not events:
        message = "暂无待恢复任务。" if run_id is None else f"未找到待恢复 run：{run_id}"
        typer.echo(message)
        raise typer.Exit(0)
    _render(events, False)
    raise typer.Exit(0)


@recover_app.command("list")
def recover_list(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    _inspect_recovery(None, json_output)


@recover_app.command("show")
def recover_show(
    run_id: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _inspect_recovery(run_id, json_output)


def _drive_recovery(command: InspectRecovery | ResumeRun | AbandonRun, json_output: bool) -> None:
    try:
        deps = build_runtime(Path.cwd())
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(5) from exc
    presenter = HumanPresenter(typer.echo)

    def decide(request: EventEnvelope) -> ApprovalDecision:
        if json_output or not sys.stdin.isatty():
            return "cancel"
        decision = typer.prompt(presenter.approval_prompt(request))
        if decision not in {"approve", "reject", "cancel"}:
            raise typer.BadParameter("必须明确输入 approve、reject 或 cancel")
        return cast(ApprovalDecision, decision)

    events = list(
        drive_run(
            deps.runtime,
            command,
            decide,
            lambda batch: _render(list(batch), json_output),
        )
    )
    raise typer.Exit(_exit_code(events) if events else 5)


@recover_app.command("resume")
def recover_resume(
    run_id: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _drive_recovery(ResumeRun(run_id=run_id), json_output)


@recover_app.command("abandon")
def recover_abandon(
    run_id: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _drive_recovery(AbandonRun(run_id=run_id), json_output)


@state_app.command("inspect")
def state_inspect(
    run_id: Annotated[str | None, typer.Argument()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        deps = build_runtime(Path.cwd())
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(5) from exc
    events = list(deps.runtime.handle(InspectState(run_id=run_id)))
    _render(events, json_output)
    raise typer.Exit(0 if events else 5)


@state_app.command("migrate")
def state_migrate(
    run_id: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    migration_hash: Annotated[str | None, typer.Option("--migration-hash")] = None,
    migration_id: Annotated[str | None, typer.Option("--migration-id")] = None,
) -> None:
    try:
        deps = build_runtime(Path.cwd())
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(5) from exc
    if not apply:
        events = list(deps.runtime.handle(PlanStateMigration(run_id=run_id)))
        _render(events, json_output)
        raise typer.Exit(0 if events and events[-1].type == "state.migration_planned" else 5)
    if not migration_hash or not migration_id:
        typer.echo("--apply 需要同时提供 --migration-id 与 --migration-hash", err=True)
        raise typer.Exit(5)
    events = list(
        deps.runtime.handle(
            ApplyStateMigration(
                run_id=run_id,
                migration_id=migration_id,
                migration_hash=migration_hash,
            )
        )
    )
    _render(events, json_output)
    raise typer.Exit(0 if events and events[-1].type == "state.migration_completed" else 5)


@app.command()
def rollback(run_id: str = typer.Argument(...)) -> None:
    deps = build_runtime(Path.cwd())
    events = list(deps.runtime.handle(RollbackRun(run_id=run_id)))
    if not events:
        typer.echo(f"未找到可回滚的 Checkpoint：{run_id}")
        raise typer.Exit(5)
    _render(events, False)
    raise typer.Exit(_exit_code(events))


@config_app.command("show")
def config_show() -> None:
    config = load_config(Path.cwd(), {})
    typer.echo(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2))
