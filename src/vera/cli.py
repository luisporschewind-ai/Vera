"""Human and JSON event CLI for the Vera Core."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, cast

import typer
from typer.core import TyperGroup

from vera.bootstrap import RuntimeDependencies, build_runtime
from vera.cli_commands import config_show as _config_show_impl
from vera.cli_commands import execute_run as _execute_run_impl
from vera.cli_commands import list_runs as _list_runs_impl
from vera.cli_commands import rollback as _rollback_impl
from vera.cli_commands import show_run as _show_run_impl
from vera.cli_driver import drive_run
from vera.cli_eval import eval_app
from vera.cli_inspection import sessions_inspect as _sessions_inspect_impl
from vera.cli_inspection import sessions_repair as _sessions_repair_impl
from vera.cli_inspection import state_inspect as _state_inspect_impl
from vera.cli_inspection import state_migrate as _state_migrate_impl
from vera.cli_json_session import JsonSessionDriver
from vera.cli_models import models_app
from vera.cli_options import RESUME_PICKER_VALUE, normalize_resume_argv
from vera.cli_plain_session import PlainSessionDriver
from vera.cli_presenter import HumanPresenter
from vera.cli_recovery import drive_recovery as _drive_recovery_impl
from vera.cli_recovery import inspect_recovery as _inspect_recovery_impl
from vera.config import ConfigurationError, load_config
from vera.contracts.commands import (
    AbandonRun,
    InspectRecovery,
    ResumeRun,
)
from vera.contracts.events import EventEnvelope
from vera.persistence.run_store import RunStore
from vera.persistence.session_store import ConversationSessionStore
from vera.redaction import Redactor
from vera.runtime.prompts import PROJECT_INIT_GOAL
from vera.session.controller import SessionController
from vera.session.startup import (
    SessionOpenRequest,
    SessionStartupError,
    SessionStartupService,
)
from vera.terminal.mode import (
    PresentationMode,
    TerminalCapabilities,
    TerminalModeError,
    select_mode,
)
from vera.version import current_identity


class SessionFlagGroup(TyperGroup):
    """Accept bare ``-r``/``--resume`` as the TTY picker, matching session specs."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        return super().parse_args(ctx, normalize_resume_argv(args))


app = typer.Typer(
    cls=SessionFlagGroup,
    invoke_without_command=True,
    no_args_is_help=False,
    help="Vera local coding-agent Core",
)
runs_app = typer.Typer(help="inspect private run records")
config_app = typer.Typer(help="inspect effective configuration")
recover_app = typer.Typer(help="inspect and recover interrupted runs")
state_app = typer.Typer(help="inspect and migrate private run state formats")
sessions_app = typer.Typer(help="inspect and repair conversation sessions")
app.add_typer(runs_app, name="runs")
app.add_typer(config_app, name="config")
app.add_typer(models_app, name="models")
app.add_typer(recover_app, name="recover")
app.add_typer(state_app, name="state")
app.add_typer(eval_app, name="eval")
app.add_typer(sessions_app, name="sessions")


def _fail_runtime_setup(exc: Exception) -> NoReturn:
    if isinstance(exc, ConfigurationError):
        typer.echo(str(exc), err=True)
        raise typer.Exit(exc.exit_code) from exc
    typer.echo(str(exc), err=True)
    raise typer.Exit(5) from exc


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
    version: Annotated[
        bool,
        typer.Option("--version", "-V", help="显示安装版本与位置并退出"),
    ] = False,
    continue_session: Annotated[
        bool,
        typer.Option("-c", "--continue", help="继续当前工作区最近的可恢复会话"),
    ] = False,
    resume: Annotated[
        str | None,
        typer.Option(
            "-r",
            "--resume",
            help="恢复会话 [SESSION_ID]；省略 ID 时在 TTY 中选择。"
            " /resume <run-id> 继续可恢复 Run。",
        ),
    ] = None,
) -> None:
    """Start an interactive session when no subcommand is supplied."""

    if version:
        identity = current_identity()
        if json_output:
            typer.echo(json.dumps(identity.to_payload(), ensure_ascii=False, sort_keys=True))
        else:
            typer.echo(identity.to_text())
        raise typer.Exit(0)
    if ctx.invoked_subcommand is not None:
        return
    resolved = workspace.resolve()
    if not resolved.is_dir():
        typer.echo(f"工作区必须是现有目录：{resolved}")
        raise typer.Exit(2)
    try:
        if continue_session and resume is not None:
            raise SessionStartupError(
                "continue_resume_conflict",
                "-c/--continue 与 -r/--resume 不能同时使用",
            )
        if continue_session:
            request = SessionOpenRequest(mode="continue")
        elif resume is None:
            request = SessionOpenRequest(mode="new")
        elif resume in {RESUME_PICKER_VALUE, ""}:
            request = SessionOpenRequest(mode="resume_picker")
        else:
            request = SessionOpenRequest(mode="resume_id", session_id=resume)
    except SessionStartupError as exc:
        _fail_session_startup(exc, json_output=json_output)
    try:
        deps = build_runtime(resolved, model)
    except Exception as exc:
        _fail_runtime_setup(exc)
    selected_model = model or next(iter(deps.config.providers), "default")
    capabilities = detect_terminal_capabilities()
    try:
        mode = select_mode(plain=plain, json_output=json_output, capabilities=capabilities)
    except TerminalModeError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(exc.exit_code) from exc
    store = ConversationSessionStore(deps.config.state_dir, deps.installation_id)
    startup = SessionStartupService(store)
    interactive = capabilities.stdin_tty and capabilities.stdout_tty
    request = _maybe_pick_session(request, store, resolved, mode, interactive, json_output)
    try:
        loaded = startup.resolve(request, resolved, interactive_tty=interactive)
    except SessionStartupError as exc:
        _fail_session_startup(exc, json_output=json_output)
    source = startup.source_for(request)
    controller = SessionController(
        deps,
        resolved,
        selected_model,
        session_store=store,
        loaded_session=loaded,
        source=source,
    )
    if mode is PresentationMode.JSON:
        raise typer.Exit(
            JsonSessionDriver(deps, resolved, selected_model, controller=controller).run(
                sys.stdin, sys.stdout
            )
        )
    if mode is PresentationMode.PLAIN:
        raise typer.Exit(
            PlainSessionDriver(
                deps, resolved, selected_model, _ConsoleSessionIO(), controller=controller
            ).run()
        )
    raise typer.Exit(_launch_tui_session(deps, resolved, selected_model, controller))


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


def _fail_session_startup(exc: SessionStartupError, *, json_output: bool) -> NoReturn:
    if json_output:
        event = {
            "schema_version": 1,
            "record_type": "event",
            "event": {
                "type": "session.load_failed",
                "payload": {
                    "error_code": exc.code,
                    "advice": exc.advice,
                },
            },
        }
        typer.echo(json.dumps(event, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(exc.message, err=True)
        if exc.advice and exc.advice != exc.message:
            typer.echo(exc.advice, err=True)
    raise typer.Exit(2) from exc


def _maybe_pick_session(
    request: SessionOpenRequest,
    store: ConversationSessionStore,
    workspace: Path,
    mode: PresentationMode,
    interactive: bool,
    json_output: bool,
) -> SessionOpenRequest:
    if request.mode != "resume_picker":
        return request
    summaries = store.list_for_workspace(workspace)
    if mode is PresentationMode.JSON or not interactive:
        payload = {
            "type": "session.listed",
            "payload": {
                "items": [
                    {
                        "session_id": item.session_id,
                        "title": item.title,
                        "recoverable": item.recoverable,
                    }
                    for item in summaries
                ]
            },
        }
        if json_output or mode is PresentationMode.JSON:
            typer.echo(
                json.dumps(
                    {"schema_version": 1, "record_type": "event", "event": payload},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            typer.echo("非交互环境请使用 vera -r <session-id>。", err=True)
            for item in summaries:
                typer.echo(f"{item.session_id}\t{item.title}", err=True)
        _fail_session_startup(
            SessionStartupError(
                "picker_requires_id",
                "非交互环境不能打开会话选择器",
                advice="请传入 vera -r <session-id>。",
            ),
            json_output=json_output or mode is PresentationMode.JSON,
        )
    from vera.terminal.widgets.session_picker import pick_session_id

    selected = pick_session_id(summaries, plain=mode is PresentationMode.PLAIN)
    if not selected:
        raise typer.Exit(2)
    return SessionOpenRequest(mode="resume_id", session_id=selected)


def _launch_tui_session(
    dependencies: RuntimeDependencies,
    workspace: Path,
    model_profile: str,
    controller: SessionController | None = None,
) -> int:
    try:
        from vera.terminal.app import launch_tui
    except Exception as exc:
        typer.echo(
            f"无法启动 Textual TUI（{exc}）。请改用 --plain。",
            err=True,
        )
        return 2
    session = controller or SessionController(dependencies, workspace, model_profile)
    try:
        return launch_tui(session, workspace, model_profile)
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
    from vera.cli_exit_codes import exit_code_for_events

    return exit_code_for_events(events)


def execute_run(
    goal: str,
    workspace: Path,
    model_profile: str | None,
    json_output: bool,
    dependencies: RuntimeDependencies | None = None,
    *,
    mode: Literal["agent", "project_init"] = "agent",
) -> int:
    return _execute_run_impl(
        goal,
        workspace,
        model_profile,
        json_output,
        dependencies,
        mode=mode,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        presenter_cls=HumanPresenter,
        drive_run_fn=drive_run,
        render=_render,
        exit_code=_exit_code,
        echo=typer.echo,
        prompt=typer.prompt,
        stdin_isatty=sys.stdin.isatty,
    )


@app.command()
def run(
    goal: str,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    model: Annotated[str | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    raise typer.Exit(execute_run(goal, workspace.resolve(), model, json_output))


@app.command(help="只提议 VERA.md，批准后写入")
def init(
    workspace: Annotated[Path, typer.Option()] = Path("."),
    model: Annotated[str | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """只提议 VERA.md，批准后写入。"""

    raise typer.Exit(
        execute_run(
            PROJECT_INIT_GOAL,
            workspace.resolve(),
            model,
            json_output,
            mode="project_init",
        )
    )


@runs_app.command("list")
def list_runs() -> None:
    _list_runs_impl(
        cwd=Path.cwd(),
        load_config_fn=load_config,
        run_store_cls=RunStore,
        echo=typer.echo,
    )


@runs_app.command("show")
def show_run(run_id: str) -> None:
    _show_run_impl(
        run_id,
        cwd=Path.cwd(),
        load_config_fn=load_config,
        run_store_cls=RunStore,
        redactor_cls=Redactor,
        echo=typer.echo,
    )


def _inspect_recovery(run_id: str | None, json_output: bool) -> None:
    _inspect_recovery_impl(
        run_id,
        json_output,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        render=_render,
        echo=typer.echo,
    )


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
    _drive_recovery_impl(
        command,
        json_output,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        presenter_cls=HumanPresenter,
        drive_run_fn=drive_run,
        render=_render,
        exit_code=_exit_code,
        echo=typer.echo,
        prompt=typer.prompt,
        stdin_isatty=sys.stdin.isatty,
    )


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
    _state_inspect_impl(
        run_id,
        json_output,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        render=_render,
    )


@state_app.command("migrate")
def state_migrate(
    run_id: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    migration_hash: Annotated[str | None, typer.Option("--migration-hash")] = None,
    migration_id: Annotated[str | None, typer.Option("--migration-id")] = None,
) -> None:
    _state_migrate_impl(
        run_id,
        json_output,
        apply,
        migration_hash,
        migration_id,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        render=_render,
        echo=typer.echo,
    )


@app.command()
def rollback(run_id: str = typer.Argument(...)) -> None:
    _rollback_impl(
        run_id,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        render=_render,
        exit_code=_exit_code,
        echo=typer.echo,
    )


@config_app.command("show")
def config_show() -> None:
    _config_show_impl(cwd=Path.cwd(), load_config_fn=load_config, echo=typer.echo)


@sessions_app.command("inspect")
def sessions_inspect(
    session_id: str,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _sessions_inspect_impl(
        session_id,
        workspace,
        json_output,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        echo=typer.echo,
    )


@sessions_app.command("repair")
def sessions_repair(
    session_id: str,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    json_output: Annotated[bool, typer.Option("--json")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
) -> None:
    _sessions_repair_impl(
        session_id,
        workspace,
        json_output,
        apply,
        build_runtime_fn=build_runtime,
        fail_runtime_setup=_fail_runtime_setup,
        echo=typer.echo,
    )
