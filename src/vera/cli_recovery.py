"""Recovery command implementations for the CLI façade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn, cast

import typer

from vera.cli_driver import ApprovalDecision, drive_run
from vera.contracts.commands import AbandonRun, InspectRecovery, ResumeRun
from vera.contracts.events import EventEnvelope


def inspect_recovery(
    run_id: str | None,
    json_output: bool,
    *,
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    render: Any,
    echo: Any,
) -> NoReturn:
    try:
        deps = build_runtime_fn(Path.cwd())
    except Exception as exc:
        fail_runtime_setup(exc)
    events = list(deps.runtime.handle(InspectRecovery(run_id=run_id)))
    if json_output:
        render(events, True)
        raise typer.Exit(0)
    if not events:
        message = "暂无待恢复任务。" if run_id is None else f"未找到待恢复 run：{run_id}"
        echo(message)
        raise typer.Exit(0)
    render(events, False)
    raise typer.Exit(0)


def drive_recovery(
    command: InspectRecovery | ResumeRun | AbandonRun,
    json_output: bool,
    *,
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    presenter_cls: Any,
    drive_run_fn: Any = drive_run,
    render: Any,
    exit_code: Any,
    echo: Any,
    prompt: Any,
    stdin_isatty: Any,
) -> NoReturn:
    try:
        deps = build_runtime_fn(Path.cwd())
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

    events = list(
        drive_run_fn(
            deps.runtime,
            command,
            decide,
            lambda batch: render(list(batch), json_output),
        )
    )
    raise typer.Exit(exit_code(events) if events else 5)


__all__ = ["drive_recovery", "inspect_recovery"]
