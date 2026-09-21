"""Session command handlers and diagnostic projections."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vera.contracts.commands import StartRun
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.workspace_permissions import (
    WorkspacePermissionStore,
    WorkspacePermissionStoreError,
)
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.project_instructions import format_instruction_status, public_instruction_facts
from vera.runtime.prompts import PROJECT_INIT_GOAL
from vera.session.permissions import permission_status

if TYPE_CHECKING:
    from vera.session.controller import SessionController


def help(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield host._session_event("session.help", {"text": host._help_text()})


def status(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield host._status_event()


def context(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    stats = host.conversation_stats()
    yield host._session_event(
        "session.context",
        stats.model_dump(mode="json"),
    )


def permissions(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    if args:
        requested = args[0].casefold()
        current = host.dependencies.runtime.workspace_permissions
        if current is None:
            yield host._session_event(
                "session.action_rejected",
                {
                    "reason_code": "permissions_unavailable",
                    "message": "当前没有工作区权限快照。",
                },
            )
            return
        if requested not in {"trust", "revoke"}:
            yield host._session_event(
                "session.message",
                {"text": "用法：/permissions [trust|revoke]"},
            )
            return
        snapshot = host.dependencies.runtime.policy_engine.snapshot
        if not isinstance(snapshot, EffectivePolicySnapshotV2):
            yield host._session_event(
                "session.action_rejected",
                {
                    "reason_code": "permissions_unavailable",
                    "message": "当前策略版本不支持工作区权限持久化。",
                },
            )
            return
        store = WorkspacePermissionStore(
            host.dependencies.config.state_dir,
            policy_major_version=snapshot.builtin_policy_version,
            protected_roots_hash=snapshot.protected_roots_hash,
        )
        updated = current.model_copy(
            update={
                "trusted": requested == "trust",
                "grants": current.grants if requested == "trust" else (),
            }
        )
        try:
            if requested == "trust":
                store.save(updated)
            else:
                store.revoke(current.workspace_identity)
        except WorkspacePermissionStoreError as exc:
            yield host._session_event(
                "session.action_rejected",
                {
                    "reason_code": exc.code,
                    "message": "工作区权限状态未更新，请检查私有状态目录。",
                },
            )
            return
        host.dependencies.runtime.workspace_permissions = updated
    status = permission_status(
        host.dependencies.runtime.command_policy,
        workspace_permissions=host.dependencies.runtime.workspace_permissions,
    )
    yield host._session_event("session.permissions", status.model_dump(mode="json"))


def instructions(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    loaded = host.dependencies.project_instructions.load(host.workspace)
    facts = public_instruction_facts(loaded)
    pending = (
        host._run_guidance_hash is not None and host._run_guidance_hash != loaded.guidance_hash
    )
    payload: dict[str, object] = {
        **facts,
        "run_guidance_hash": host._run_guidance_hash,
        "not_found": not loaded.sources and not loaded.issues,
        "pending_next_run": pending,
    }
    payload["text"] = format_instruction_status(payload)
    yield host._session_event("project.instructions.status", payload)


def init(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    if host._active_run_id is not None:
        pending = host._pending_approval is not None
        yield host._session_event(
            "session.action_rejected",
            {
                "reason_code": "approval_pending" if pending else "run_active",
                "message": (
                    "等待审批时不能启动初始化。"
                    if pending
                    else "当前有运行中的任务，请先等待、取消或完成审批。"
                ),
            },
        )
        return
    command = StartRun(
        goal=PROJECT_INIT_GOAL,
        workspace_root=host.workspace,
        model_profile=host.model_profile,
        conversation=host.conversation.snapshot(),
        mode="project_init",
    )
    host._goal_for_active = PROJECT_INIT_GOAL
    host._events_for_active = []
    yield from host._drive(command)


def sessions(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    summaries = host.session_store.list_for_workspace(host.workspace)
    items = [
        {
            "session_id": item.session_id,
            "title": item.title,
            "updated_at": item.updated_at.isoformat().replace("+00:00", "Z"),
            "message_count": item.message_count,
            "recoverable": item.recoverable,
            "latest_run_state": item.latest_run_state,
        }
        for item in summaries
    ]
    lines = [
        f"{item['session_id']}\t{item['title']}\t{item['message_count']}" for item in items
    ] or ["当前工作区没有会话。"]
    yield host._session_event(
        "session.listed",
        {"items": items, "text": "\n".join(lines)},
    )


def new(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._begin_fresh_session("已开始新会话：{session_id}")


def clear(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._begin_fresh_session("已清空显示并开始新会话：{session_id}")


def begin_fresh_session(host: SessionController, message: str) -> Iterator[RuntimeOutput]:
    session_id = host._open_new_persistent_session()
    host.clear_display_requested = True
    yield host._session_event(
        "session.message",
        {
            "clear_display": True,
            "text": message.format(session_id=session_id),
        },
    )


def compact(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._compact(" ".join(args) if args else "保留关键结论与未完成事项")


def model(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._switch_model(args[0] if args else None)


def runs(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._write_runs()


def show(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._show(args[0])


def rollback(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._rollback(args[0])


def recover(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._recover(args[0] if args else None)


def resume(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._resume(args[0])


def abandon(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._abandon(args[0])


def exit(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    yield from host._close()


def diff(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    from vera.session.queries import collect_diffs, resolve_run_id

    run_id = resolve_run_id(host.store, args[0] if args else None, host._active_run_id)
    events = host._events_for_run(run_id)
    files = collect_diffs(events)
    applied = any(event.type == "changeset.applied" for event in events)
    if not files:
        yield host._session_event(
            "session.diff",
            {"run_id": run_id, "files": [], "applied": applied, "text": "没有 Diff。"},
        )
        return
    parts: list[str] = []
    for item in files:
        path = str(item.get("path", "")).strip()
        diff = str(item.get("unified_diff", "")).rstrip()
        if path and diff:
            parts.append(f"{path}\n{diff}")
        elif diff:
            parts.append(diff)
    body = "\n\n".join(parts) or "没有 Diff。"
    if not applied:
        body = "这是提案 Diff，未写入工作区。\n\n" + body
    yield host._session_event(
        "session.diff",
        {"run_id": run_id, "files": list(files), "applied": applied, "text": body},
    )


def review(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    from vera.presentation.review import project_review
    from vera.session.queries import resolve_run_id

    run_id = resolve_run_id(host.store, args[0] if args else None, host._active_run_id)
    events = host._events_for_run(run_id)
    review = project_review(events)
    review["run_id"] = run_id
    yield host._session_event("session.review", review)


def doctor(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    import os
    from pathlib import Path as ConfigPath

    from platformdirs import user_config_path

    from vera.session.diagnostics import doctor_report

    user_config = ConfigPath(
        os.environ.get("VERA_USER_CONFIG_FILE", str(user_config_path("Vera") / "config.toml"))
    )
    report = doctor_report(
        workspace=host.workspace,
        state_dir=host.dependencies.config.state_dir,
        user_config=user_config,
    )
    yield host._session_event("session.doctor", report)


def config(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    import os
    from pathlib import Path as ConfigPath

    from platformdirs import user_config_path

    from vera.session.diagnostics import redacted_config_view

    user_file = ConfigPath(
        os.environ.get(
            "VERA_USER_CONFIG_FILE",
            str(user_config_path("Vera") / "config.toml"),
        )
    )
    project_file = host.workspace / ".vera" / "config.toml"
    sources = {
        "user": str(user_file) if user_file.is_file() else "absent",
        "project": str(project_file) if project_file.is_file() else "absent",
        "environment": "applied",
        "cli": "overrides",
    }
    yield host._session_event(
        "session.config",
        redacted_config_view(host.dependencies.config, sources),
    )


def usage(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    from vera.session.queries import usage_snapshot

    events = tuple(host._events_for_active)
    for summary in host.store.list_runs():
        events = events + tuple(host.store.read_events(summary.run_id))
    yield host._session_event("session.usage", usage_snapshot(events))


def shortcuts(host: SessionController, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    from vera.session.diagnostics import shortcut_list

    items = shortcut_list()
    text = "\n".join(f"{item['keys']}\t{item['action']}" for item in items)
    yield host._session_event(
        "session.shortcuts",
        {"items": [dict(item) for item in items], "text": text},
    )


def theme(host: SessionController, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
    from vera.terminal.theme import THEME_NAMES, format_theme_status, normalize_theme

    if not args:
        yield host._session_event(
            "session.theme",
            {
                "theme": host.theme,
                "available": list(THEME_NAMES),
                "text": format_theme_status(host.theme),
            },
        )
        return
    selected = normalize_theme(args[0], host.theme)  # type: ignore[arg-type]
    if selected is None:
        yield host._session_event(
            "session.message",
            {"text": f"未知主题：{args[0]}。可用：{', '.join(THEME_NAMES)}"},
        )
        return
    host.theme = selected
    yield host._session_event(
        "session.theme",
        {
            "theme": host.theme,
            "available": list(THEME_NAMES),
            "text": format_theme_status(host.theme),
        },
    )


def help_text(host: SessionController) -> str:
    from vera.session.command_catalog import CommandCatalog

    return CommandCatalog().help_text(host.snapshot())


class SessionInspectionFlow:
    """Stable façade for command handlers and inspection projections."""

    help = staticmethod(help)
    status = staticmethod(status)
    context = staticmethod(context)
    permissions = staticmethod(permissions)
    instructions = staticmethod(instructions)
    init = staticmethod(init)
    sessions = staticmethod(sessions)
    new = staticmethod(new)
    clear = staticmethod(clear)
    begin_fresh_session = staticmethod(begin_fresh_session)
    compact = staticmethod(compact)
    model = staticmethod(model)
    runs = staticmethod(runs)
    show = staticmethod(show)
    rollback = staticmethod(rollback)
    recover = staticmethod(recover)
    resume = staticmethod(resume)
    abandon = staticmethod(abandon)
    exit = staticmethod(exit)
    diff = staticmethod(diff)
    review = staticmethod(review)
    doctor = staticmethod(doctor)
    config = staticmethod(config)
    usage = staticmethod(usage)
    shortcuts = staticmethod(shortcuts)
    theme = staticmethod(theme)
    help_text = staticmethod(help_text)
