"""Slash command parsing and run-management flow."""

from __future__ import annotations

import shlex
from collections.abc import Iterator
from typing import TYPE_CHECKING

from vera.contracts.commands import AbandonRun, InspectRecovery, ResumeRun, RollbackRun, StartRun
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.run_store import RunStore
from vera.session.flow_constants import _TERMINAL_TYPES

if TYPE_CHECKING:
    from vera.session.controller import SessionController


def slash(host: SessionController, raw: str) -> Iterator[RuntimeOutput]:
    if host._active_run_id is not None and host._pending_approval is None:
        yield host._session_event(
            "session.action_rejected",
            {"reason_code": "run_active", "message": "当前有运行中的任务。"},
        )
        return
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        yield host._session_event("session.message", {"text": f"命令格式错误：{exc}"})
        return
    if not parts:
        return
    from vera.session.command_catalog import CommandCatalog

    catalog = CommandCatalog()
    parsed = catalog.parse(parts)
    if parsed.unknown:
        hint = f" 候选：{', '.join(parsed.suggestions)}。" if parsed.suggestions else ""
        yield host._session_event(
            "session.message",
            {
                "text": f"未知命令：{parsed.name}。{hint}输入 /help 查看可用命令。",
                "suggestions": list(parsed.suggestions),
            },
        )
        return
    descriptor = catalog.get(parsed.name)
    if descriptor is not None and descriptor.args == "none" and parsed.args:
        yield host._session_event("session.message", {"text": f"用法：{descriptor.usage}"})
        return
    if descriptor is not None and descriptor.args == "required" and not parsed.args:
        text = f"用法：{descriptor.usage}"
        hint = host._required_run_id_hint(parsed.handler)
        if hint:
            text = f"{text}\n{hint}"
        yield host._session_event("session.message", {"text": text})
        return
    if (
        descriptor is not None
        and descriptor.args == "optional"
        and parsed.handler not in {"compact"}
        and len(parsed.args) > 1
    ):
        yield host._session_event("session.message", {"text": f"用法：{descriptor.usage}"})
        return
    handler = getattr(host, f"_cmd_{parsed.handler}", None)
    if handler is None:
        yield host._session_event(
            "session.message",
            {"text": f"未知命令：{parsed.name}。输入 /help 查看可用命令。"},
        )
        return
    yield from handler(parsed.args)


def compact(host: SessionController, focus: str) -> Iterator[RuntimeOutput]:
    before = host.conversation.snapshot()
    if not before:
        yield host._session_event("session.message", {"text": "当前上下文为空，无需压缩。"})
        return
    yield host._session_event("session.message", {"text": "正在压缩上下文…"})
    host._goal_for_active = None
    host._events_for_active = []
    collected: list[EventEnvelope] = []
    for output in host._drive(
        StartRun(
            goal=focus,
            workspace_root=host.workspace,
            model_profile=host.model_profile,
            mode="compact",
            conversation=before,
        ),
        record_conversation=False,
    ):
        if isinstance(output, EventEnvelope):
            collected.append(output)
        yield output
    if host._pending_approval is not None:
        return
    compacted = next(
        (event for event in collected if event.type == "conversation.compacted"),
        None,
    )
    completed = next(
        (event for event in reversed(collected) if event.type in _TERMINAL_TYPES),
        None,
    )
    summary = compacted.payload.get("summary") if compacted is not None else None
    if (
        compacted is not None
        and isinstance(summary, str)
        and summary.strip()
        and completed is not None
        and completed.type == "run.completed"
        and completed.payload.get("outcome") == "compacted"
    ):
        yield from host._persist_compaction(summary)
        return
    assert host.conversation.snapshot() == before
    yield host._session_event("session.message", {"text": "上下文压缩失败，已保留原上下文。"})


def switch_model(host: SessionController, requested_profile: str | None) -> Iterator[RuntimeOutput]:
    if requested_profile is None:
        yield host._session_event(
            "session.message",
            {"text": f"当前模型：{host.model_profile} / {host._model_name()}"},
        )
        return
    try:
        candidate = host.runtime_builder(host.workspace, requested_profile)
    except Exception as exc:
        yield host._session_event(
            "session.message",
            {"text": f"模型切换失败，已保留当前配置：{exc}"},
        )
        return
    host.dependencies = candidate
    host.model_profile = requested_profile
    host.store = RunStore(candidate.config.state_dir)
    yield host._session_event(
        "session.message",
        {"text": f"已切换模型：{host.model_profile} / {host._model_name()}"},
    )


def write_runs(host: SessionController) -> Iterator[RuntimeOutput]:
    summaries = host.store.list_runs()
    if not summaries:
        yield host._session_event("session.message", {"text": "暂无 run。"})
        return
    lines = [
        f"{summary.run_id}\t{summary.goal_summary}\t{summary.terminal_state or 'active'}"
        for summary in summaries
    ]
    yield host._session_event("session.message", {"text": "\n".join(lines)})


def show(host: SessionController, run_id: str) -> Iterator[RuntimeOutput]:
    events = host.store.read_events(run_id)
    if not events:
        yield host._session_event("session.message", {"text": f"未找到 run：{run_id}"})
        return
    yield from events


def rollback(host: SessionController, run_id: str) -> Iterator[RuntimeOutput]:
    events = tuple(host.dependencies.runtime.handle(RollbackRun(run_id=run_id)))
    if not events:
        yield host._session_event(
            "session.message",
            {"text": f"未找到可回滚的 Checkpoint：{run_id}"},
        )
        return
    yield from events


def recover(host: SessionController, run_id: str | None) -> Iterator[RuntimeOutput]:
    events = tuple(host.dependencies.runtime.handle(InspectRecovery(run_id=run_id)))
    if not events:
        if run_id is None:
            yield host._session_event("session.message", {"text": "暂无待恢复任务。"})
        else:
            yield host._session_event(
                "session.message",
                {"text": f"未找到待恢复 run：{run_id}"},
            )
        return
    yield from events


def resume(host: SessionController, run_id: str) -> Iterator[RuntimeOutput]:
    host._goal_for_active = None
    host._events_for_active = []
    outputs = list(host._drive(ResumeRun(run_id=run_id)))
    if not outputs and host._active_run_id is None and host._pending_approval is None:
        yield host._session_event("session.message", {"text": f"未找到可恢复 run：{run_id}"})
        return
    yield from outputs


def abandon(host: SessionController, run_id: str) -> Iterator[RuntimeOutput]:
    events = tuple(host.dependencies.runtime.handle(AbandonRun(run_id=run_id)))
    if not events:
        yield host._session_event("session.message", {"text": f"未找到可放弃 run：{run_id}"})
        return
    yield from events


def required_run_id_hint(host: SessionController, handler: str) -> str:
    if handler not in {"abandon", "resume"}:
        return ""
    reports = host.dependencies.runtime.coordinator.scan()
    matching = [item for item in reports if handler in item.allowed_actions]
    if matching:
        lines = [f"可 {handler}："]
        lines.extend(f"{item.run_id}（{item.classification.value}）" for item in matching)
        return "\n".join(lines)
    if reports:
        return f"当前没有可 {handler} 的待恢复任务。使用 /recover 查看需要人工处理的 run。"
    return "当前没有待恢复任务。"


class SessionCommandFlow:
    """Stable façade for slash command routing and run management."""

    slash = staticmethod(slash)
    compact = staticmethod(compact)
    switch_model = staticmethod(switch_model)
    write_runs = staticmethod(write_runs)
    show = staticmethod(show)
    rollback = staticmethod(rollback)
    recover = staticmethod(recover)
    resume = staticmethod(resume)
    abandon = staticmethod(abandon)
    required_run_id_hint = staticmethod(required_run_id_hint)
