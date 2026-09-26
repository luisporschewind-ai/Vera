"""Human and JSON event CLI for the Vera Core."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, cast

import typer
from typer.core import TyperGroup

from vera.bootstrap import RuntimeDependencies, build_runtime
from vera.cli_driver import ApprovalDecision, drive_run
from vera.cli_eval import eval_app
from vera.cli_json_session import JsonSessionDriver
from vera.cli_models import models_app
from vera.cli_options import RESUME_PICKER_VALUE, normalize_resume_argv
from vera.cli_plain_session import PlainSessionDriver
from vera.cli_presenter import HumanPresenter
from vera.config import ConfigurationError, load_config
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
app.add_typer(recover_app, name="recover")
app.add_typer(state_app, name="state")
app.add_typer(eval_app, name="eval")
app.add_typer(sessions_app, name="sessions")
app.add_typer(models_app, name="models")


def _fail_runtime_setup(exc: Exception) -> NoReturn:
    if isinstance(exc, ConfigurationError):
        typer.echo(str(exc), err=True)
        raise typer.Exit(exc.exit_code) from exc
    typer.echo("configuration_failed: runtime configuration is invalid", err=True)
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
    selected_model = (
        model or deps.config.default_model_profile or next(iter(deps.config.providers), "default")
    )
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
    try:
        deps = dependencies or build_runtime(workspace, model_profile)
    except Exception as exc:
        _fail_runtime_setup(exc)
    presenter = HumanPresenter(typer.echo)

    def decide(request: EventEnvelope) -> ApprovalDecision:
        if json_output or not sys.stdin.isatty():
            return "cancel"
        decision = typer.prompt(presenter.approval_prompt(request))
        if decision not in {"approve", "reject", "cancel"}:
            raise typer.BadParameter("必须明确输入 approve、reject 或 cancel")
        return cast(ApprovalDecision, decision)

    selected = model_profile or next(iter(deps.config.providers), "default")
    events = drive_run(
        deps.runtime,
        StartRun(
            goal=goal,
            workspace_root=workspace,
            model_profile=selected,
            mode=mode,
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
    config = load_config(Path.cwd(), {})
    for summary in RunStore(config.state_dir).list_runs():
        typer.echo(f"{summary.run_id}\t{summary.workspace_root}\t{summary.terminal_state}")


@runs_app.command("show")
def show_run(run_id: str) -> None:
    config = load_config(Path.cwd(), {})
    for event in RunStore(config.state_dir).read_events(run_id):
        typer.echo(Redactor().redact_event(event).model_dump_json())


def _inspect_recovery(run_id: str | None, json_output: bool) -> None:
    try:
        deps = build_runtime(Path.cwd())
    except Exception as exc:
        _fail_runtime_setup(exc)
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
        _fail_runtime_setup(exc)
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
        _fail_runtime_setup(exc)
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
        _fail_runtime_setup(exc)
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
    try:
        deps = build_runtime(Path.cwd())
    except Exception as exc:
        _fail_runtime_setup(exc)
    events = list(deps.runtime.handle(RollbackRun(run_id=run_id)))
    if not events:
        typer.echo(f"未找到可回滚的 Checkpoint：{run_id}")
        raise typer.Exit(5)
    _render(events, False)
    raise typer.Exit(_exit_code(events))


@config_app.command("show")
def config_show() -> None:
    try:
        config = load_config(Path.cwd(), {})
    except Exception as exc:
        _fail_runtime_setup(exc)
    typer.echo(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2))


@sessions_app.command("inspect")
def sessions_inspect(
    session_id: str,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        deps = build_runtime(workspace)
    except Exception as exc:
        _fail_runtime_setup(exc)
    store = ConversationSessionStore(deps.config.state_dir, deps.installation_id)
    try:
        plan = store.inspect_repair(session_id, workspace.resolve())
    except Exception as exc:
        message = str(exc)
        code = getattr(exc, "code", "invalid_session_record")
        if json_output:
            typer.echo(
                json.dumps(
                    {"error_code": code, "message": message},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2) from exc
    payload = plan.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(
            f"{plan.source_session_id}\t{plan.failure_code}\t"
            f"through={plan.valid_through_sequence}\t"
            f"repairable={plan.repairable_tail_only}"
        )
    raise typer.Exit(0)


@sessions_app.command("repair")
def sessions_repair(
    session_id: str,
    workspace: Annotated[Path, typer.Option()] = Path("."),
    json_output: Annotated[bool, typer.Option("--json")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
) -> None:
    try:
        deps = build_runtime(workspace)
    except Exception as exc:
        _fail_runtime_setup(exc)
    store = ConversationSessionStore(deps.config.state_dir, deps.installation_id)
    root = workspace.resolve()
    try:
        plan = store.inspect_repair(session_id, root)
        if not apply:
            payload = plan.model_dump(mode="json")
            payload["applied"] = False
            if json_output:
                typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                typer.echo("未应用修复。使用 --apply 才会创建新副本。")
                typer.echo(
                    f"{plan.source_session_id}\t{plan.failure_code}\t"
                    f"through={plan.valid_through_sequence}"
                )
            raise typer.Exit(0)
        original = (deps.config.state_dir / "sessions" / session_id / "session.jsonl").read_bytes()
        loaded = store.create_repaired_copy(plan, root)
        unchanged = (
            deps.config.state_dir / "sessions" / session_id / "session.jsonl"
        ).read_bytes() == original
        payload = {
            "source_session_id": session_id,
            "new_session_id": loaded.session_id,
            "source_unchanged": unchanged,
            "applied": True,
        }
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            typer.echo(f"新会话 {loaded.session_id}；原文件未改：{unchanged}")
        raise typer.Exit(0 if unchanged else 2)
    except typer.Exit:
        raise
    except Exception as exc:
        message = str(exc)
        code = getattr(exc, "code", "invalid_session_record")
        if json_output:
            typer.echo(
                json.dumps(
                    {"error_code": code, "message": message},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2) from exc
