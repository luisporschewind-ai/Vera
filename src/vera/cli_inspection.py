"""State and conversation-session inspection commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn

import typer

from vera.contracts.commands import ApplyStateMigration, InspectState, PlanStateMigration
from vera.persistence.session_store import ConversationSessionStore


def state_inspect(
    run_id: str | None,
    json_output: bool,
    *,
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    render: Any,
) -> NoReturn:
    try:
        deps = build_runtime_fn(Path.cwd())
    except Exception as exc:
        fail_runtime_setup(exc)
    events = list(deps.runtime.handle(InspectState(run_id=run_id)))
    render(events, json_output)
    raise typer.Exit(0 if events else 5)


def state_migrate(
    run_id: str,
    json_output: bool,
    apply: bool,
    migration_hash: str | None,
    migration_id: str | None,
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
    if not apply:
        events = list(deps.runtime.handle(PlanStateMigration(run_id=run_id)))
        render(events, json_output)
        raise typer.Exit(0 if events and events[-1].type == "state.migration_planned" else 5)
    if not migration_hash or not migration_id:
        echo("--apply 需要同时提供 --migration-id 与 --migration-hash", err=True)
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
    render(events, json_output)
    raise typer.Exit(0 if events and events[-1].type == "state.migration_completed" else 5)


def sessions_inspect(
    session_id: str,
    workspace: Path,
    json_output: bool,
    *,
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    echo: Any,
) -> NoReturn:
    try:
        deps = build_runtime_fn(workspace)
    except Exception as exc:
        fail_runtime_setup(exc)
    store = ConversationSessionStore(deps.config.state_dir, deps.installation_id)
    try:
        plan = store.inspect_repair(session_id, workspace.resolve())
    except Exception as exc:
        message = str(exc)
        code = getattr(exc, "code", "invalid_session_record")
        if json_output:
            echo(
                json.dumps(
                    {"error_code": code, "message": message},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            echo(message, err=True)
        raise typer.Exit(2) from exc
    payload = plan.model_dump(mode="json")
    if json_output:
        echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        echo(
            f"{plan.source_session_id}\t{plan.failure_code}\t"
            f"through={plan.valid_through_sequence}\t"
            f"repairable={plan.repairable_tail_only}"
        )
    raise typer.Exit(0)


def sessions_repair(
    session_id: str,
    workspace: Path,
    json_output: bool,
    apply: bool,
    *,
    build_runtime_fn: Any,
    fail_runtime_setup: Any,
    echo: Any,
) -> NoReturn:
    try:
        deps = build_runtime_fn(workspace)
    except Exception as exc:
        fail_runtime_setup(exc)
    store = ConversationSessionStore(deps.config.state_dir, deps.installation_id)
    root = workspace.resolve()
    try:
        plan = store.inspect_repair(session_id, root)
        if not apply:
            payload = plan.model_dump(mode="json")
            payload["applied"] = False
            if json_output:
                echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                echo("未应用修复。使用 --apply 才会创建新副本。")
                echo(
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
            echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            echo(f"新会话 {loaded.session_id}；原文件未改：{unchanged}")
        raise typer.Exit(0 if unchanged else 2)
    except typer.Exit:
        raise
    except Exception as exc:
        message = str(exc)
        code = getattr(exc, "code", "invalid_session_record")
        if json_output:
            echo(
                json.dumps(
                    {"error_code": code, "message": message},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            echo(message, err=True)
        raise typer.Exit(2) from exc


__all__ = ["sessions_inspect", "sessions_repair", "state_inspect", "state_migrate"]
