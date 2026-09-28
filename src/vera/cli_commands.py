"""One-shot and inspection command implementations for the CLI façade."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

import typer

from vera.bootstrap import RuntimeDependencies
from vera.cli_driver import ApprovalDecision, drive_run
from vera.contracts.commands import RollbackRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.runtime.prompts import PROJECT_INIT_GOAL


def execute_run(
    goal: str,
    workspace: Path,
    model_profile: str | None,
    json_output: bool,
    dependencies: RuntimeDependencies | None = None,
    *,
    mode: Literal["agent", "project_init"] = "agent",
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    presenter_cls: Any,
    drive_run_fn: Any = drive_run,
    render: Any,
    exit_code: Any,
    echo: Any,
    prompt: Any,
    stdin_isatty: Any,
) -> int:
    try:
        deps = dependencies or build_runtime_fn(workspace, model_profile)
    except Exception as exc:
        fail_runtime_setup(exc)
    presenter = presenter_cls(echo)

    def decide(request: EventEnvelope) -> ApprovalDecision:
        if json_output or not stdin_isatty():
            return "cancel"
        decision = prompt(presenter.approval_prompt(request))
        if decision not in {"approve", "reject", "cancel"}:
            raise typer.BadParameter("必须明确输入 approve、reject 或 cancel")
        return cast(ApprovalDecision, decision)

    selected = (
        model_profile
        or deps.config.default_model_profile
        or next(iter(deps.config.providers), "default")
    )
    events = drive_run_fn(
        deps.runtime,
        StartRun(
            goal=goal,
            workspace_root=workspace,
            model_profile=selected,
            mode=mode,
        ),
        decide,
        lambda batch: render(list(batch), json_output),
    )
    return cast(int, exit_code(list(events)))


def list_runs(*, cwd: Path, load_config_fn: Any, run_store_cls: Any, echo: Any) -> None:
    config = load_config_fn(cwd, {})
    for summary in run_store_cls(config.state_dir).list_runs():
        echo(f"{summary.run_id}\t{summary.workspace_root}\t{summary.terminal_state}")


def show_run(
    run_id: str,
    *,
    cwd: Path,
    load_config_fn: Any,
    run_store_cls: Any,
    redactor_cls: Any,
    echo: Any,
) -> None:
    config = load_config_fn(cwd, {})
    for event in run_store_cls(config.state_dir).read_events(run_id):
        echo(redactor_cls().redact_event(event).model_dump_json())


def rollback(
    run_id: str,
    *,
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    render: Any,
    exit_code: Any,
    echo: Any,
) -> None:
    try:
        deps = build_runtime_fn(Path.cwd())
    except Exception as exc:
        fail_runtime_setup(exc)
    events = list(deps.runtime.handle(RollbackRun(run_id=run_id)))
    if not events:
        echo(f"未找到可回滚的 Checkpoint：{run_id}")
        raise typer.Exit(5)
    render(events, False)
    raise typer.Exit(exit_code(events))


def config_show(*, cwd: Path, load_config_fn: Any, echo: Any) -> None:
    config = load_config_fn(cwd, {})
    echo(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2))


__all__ = [
    "PROJECT_INIT_GOAL",
    "config_show",
    "execute_run",
    "list_runs",
    "rollback",
    "show_run",
]
