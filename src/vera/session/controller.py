"""UI-independent session controller over VeraRuntime."""

from __future__ import annotations

import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vera.bootstrap import RuntimeBuilder, RuntimeDependencies, build_runtime
from vera.contracts.commands import (
    AbandonRun,
    CancelRun,
    InspectRecovery,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.run_store import RunStore
from vera.session.actions import (
    CancelActiveRun,
    CloseSession,
    ExecuteSlashCommand,
    ResolveSessionApproval,
    SessionAction,
    SubmitPrompt,
)
from vera.session.conversation import ConversationContext
from vera.session.permissions import permission_status
from vera.session.status import SessionStatusService

_TERMINAL_TYPES = frozenset(
    {
        "run.completed",
        "run.failed",
        "run.cancelled",
        "recovery.abandoned",
        "rollback.completed",
        "rollback.conflicted",
        "recovery.manual_required",
    }
)


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str
    active_run_id: str | None
    pending_approval_id: str | None
    model_profile: str
    closed: bool


class SessionController:
    """Dispatch structured SessionAction values and yield RuntimeOutput."""

    def __init__(
        self,
        dependencies: RuntimeDependencies,
        workspace: Path,
        model_profile: str,
        *,
        conversation: ConversationContext | None = None,
        status_service: SessionStatusService | None = None,
        runtime_builder: RuntimeBuilder | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.workspace = workspace.resolve()
        self.model_profile = model_profile
        self.store = RunStore(dependencies.config.state_dir)
        self.conversation = conversation or ConversationContext(
            dependencies.config.limits.max_conversation_bytes
        )
        self.status_service = status_service or SessionStatusService()
        self.runtime_builder = runtime_builder or build_runtime
        self._active_run_id: str | None = None
        self._pending_approval: EventEnvelope | None = None
        self._closed = False
        self._session_sequence = 0
        self._goal_for_active: str | None = None
        self._events_for_active: list[EventEnvelope] = []
        self.clear_display_requested = False
        self.exit_requested = False

    @property
    def active_run_id(self) -> str | None:
        return self._active_run_id

    @property
    def pending_approval_id(self) -> str | None:
        if self._pending_approval is None:
            return None
        value = self._pending_approval.payload.get("approval_id")
        return str(value) if value is not None else None

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self.conversation.stats().session_id,
            active_run_id=self._active_run_id,
            pending_approval_id=self.pending_approval_id,
            model_profile=self.model_profile,
            closed=self._closed,
        )

    def mark_active(self, run_id: str) -> None:
        """Test helper: mark a run as active without starting Core."""

        self._active_run_id = run_id

    def dispatch(self, action: SessionAction) -> Iterator[RuntimeOutput]:
        if self._closed:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "session_closed", "message": "会话已关闭。"},
            )
            return
        match action:
            case SubmitPrompt(text=text):
                yield from self._submit(text)
            case ExecuteSlashCommand(raw=raw):
                yield from self._slash(raw)
            case ResolveSessionApproval(approval_id=approval_id, decision=decision):
                yield from self._resolve_approval(approval_id, decision)
            case CancelActiveRun(run_id=run_id):
                yield from self._cancel(run_id)
            case CloseSession():
                yield from self._close()

    def _submit(self, text: str) -> Iterator[RuntimeOutput]:
        if self._active_run_id is not None:
            yield self._session_event(
                "session.action_rejected",
                {
                    "reason_code": "run_active",
                    "message": "当前有运行中的任务，请先等待、取消或完成审批。",
                },
            )
            return
        if not self.conversation.can_accept(text):
            yield self._session_event(
                "session.message",
                {"text": "当前上下文已满。请先执行 /compact 或 /new。"},
            )
            return
        command = StartRun(
            goal=text,
            workspace_root=self.workspace,
            model_profile=self.model_profile,
            conversation=self.conversation.snapshot(),
        )
        self._goal_for_active = text
        self._events_for_active = []
        yield from self._drive(command)

    def _resolve_approval(
        self, approval_id: str, decision: Literal["approve", "reject", "cancel"]
    ) -> Iterator[RuntimeOutput]:
        pending = self._pending_approval
        if pending is None or self._active_run_id is None:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "no_pending_approval", "message": "当前没有待处理审批。"},
            )
            return
        pending_id = str(pending.payload.get("approval_id", ""))
        if pending_id != approval_id:
            yield self._session_event(
                "session.action_rejected",
                {
                    "reason_code": "approval_mismatch",
                    "message": "审批 ID 不匹配。",
                    "expected": pending_id,
                    "received": approval_id,
                },
            )
            return
        run_id = self._active_run_id
        self._pending_approval = None
        if decision == "cancel":
            yield from self._drive(CancelRun(run_id=run_id))
            return
        yield from self._drive(
            ResolveApproval(
                run_id=run_id,
                approval_id=approval_id,
                target_hash=str(pending.payload["target_hash"]),
                decision=decision,
            )
        )

    def _cancel(self, run_id: str) -> Iterator[RuntimeOutput]:
        if self._active_run_id is None:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "no_active_run", "message": "当前没有可取消的任务。"},
            )
            return
        if run_id != self._active_run_id:
            yield self._session_event(
                "session.action_rejected",
                {
                    "reason_code": "run_mismatch",
                    "message": "取消目标与当前任务不一致。",
                    "active_run_id": self._active_run_id,
                    "requested_run_id": run_id,
                },
            )
            return
        self._pending_approval = None
        yield from self._drive(CancelRun(run_id=run_id))

    def _close(self) -> Iterator[RuntimeOutput]:
        if self._pending_approval is not None and self._active_run_id is not None:
            approval_id = str(self._pending_approval.payload.get("approval_id", ""))
            yield from self._resolve_approval(approval_id, "cancel")
        if self._active_run_id is not None:
            yield from self._cancel(self._active_run_id)
        self._closed = True
        self.exit_requested = True
        yield self._session_event("session.closed", {"reason": "user_close"})

    def _drive(
        self,
        command: StartRun | ResolveApproval | CancelRun | ResumeRun,
        *,
        record_conversation: bool = True,
    ) -> Iterator[RuntimeOutput]:
        produced_terminal = False
        for output in self.dependencies.runtime.stream(command):
            if isinstance(output, EventEnvelope):
                self._events_for_active.append(output)
                if output.type == "run.started" or self._active_run_id is None:
                    self._active_run_id = output.run_id
                if output.type == "approval.required":
                    self._active_run_id = output.run_id
                    self._pending_approval = output
                    yield output
                    return
                if output.type in _TERMINAL_TYPES:
                    produced_terminal = True
            yield output
        if produced_terminal or self._pending_approval is None:
            self._finish_active_run(record_conversation=record_conversation)

    def _finish_active_run(self, *, record_conversation: bool = True) -> None:
        goal = self._goal_for_active
        events = tuple(self._events_for_active)
        self._active_run_id = None
        self._pending_approval = None
        self._goal_for_active = None
        self._events_for_active = []
        if record_conversation and goal is not None and events:
            self.conversation.record_run(goal, events)

    def _slash(self, raw: str) -> Iterator[RuntimeOutput]:
        if self._active_run_id is not None and self._pending_approval is None:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "run_active", "message": "当前有运行中的任务。"},
            )
            return
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            yield self._session_event("session.message", {"text": f"命令格式错误：{exc}"})
            return
        if not parts:
            return
        command = parts[0]
        args = parts[1:]
        if command in {"/exit", "/quit"} and not args:
            yield from self._close()
            return
        if command == "/help" and not args:
            yield self._session_event("session.help", {"text": self._help_text()})
            return
        if command == "/status" and not args:
            yield self._status_event()
            return
        if command == "/context" and not args:
            stats = self.conversation.stats()
            yield self._session_event(
                "session.context",
                {
                    "session_id": stats.session_id,
                    "message_count": stats.message_count,
                    "context_bytes": stats.context_bytes,
                    "max_bytes": stats.max_bytes,
                    "warning": stats.warning,
                    "compaction_count": stats.compaction_count,
                },
            )
            return
        if command == "/permissions" and not args:
            status = permission_status(self.dependencies.runtime.command_policy)
            yield self._session_event(
                "session.permissions",
                status.model_dump(mode="json"),
            )
            return
        if command == "/new" and not args:
            session_id = self.conversation.reset()
            yield self._session_event(
                "session.message",
                {"text": f"已开始新会话：{session_id}"},
            )
            return
        if command == "/clear" and not args:
            session_id = self.conversation.reset()
            self.clear_display_requested = True
            yield self._session_event(
                "session.message",
                {"text": f"已清空显示并开始新会话：{session_id}", "clear_display": True},
            )
            return
        if command == "/compact":
            yield from self._compact(" ".join(args) if args else "保留关键结论与未完成事项")
            return
        if command == "/model" and len(args) <= 1:
            yield from self._switch_model(args[0] if args else None)
            return
        if command == "/runs" and not args:
            yield from self._write_runs()
            return
        if command == "/show" and len(args) == 1:
            yield from self._show(args[0])
            return
        if command == "/rollback" and len(args) == 1:
            yield from self._rollback(args[0])
            return
        if command == "/recover" and len(args) <= 1:
            yield from self._recover(args[0] if args else None)
            return
        if command == "/resume" and len(args) == 1:
            yield from self._resume(args[0])
            return
        if command == "/abandon" and len(args) == 1:
            yield from self._abandon(args[0])
            return
        if command in {"/show", "/rollback", "/resume", "/abandon"}:
            yield self._session_event("session.message", {"text": f"用法：{command} <run-id>"})
            return
        if command == "/model":
            yield self._session_event("session.message", {"text": "用法：/model [profile]"})
            return
        if command in {
            "/help",
            "/status",
            "/context",
            "/permissions",
            "/new",
            "/clear",
            "/compact",
            "/runs",
            "/recover",
            "/exit",
            "/quit",
        }:
            yield self._session_event("session.message", {"text": f"用法：{command}"})
            return
        yield self._session_event(
            "session.message",
            {"text": f"未知命令：{command}。输入 /help 查看可用命令。"},
        )

    def _compact(self, focus: str) -> Iterator[RuntimeOutput]:
        before = self.conversation.snapshot()
        if not before:
            yield self._session_event("session.message", {"text": "当前上下文为空，无需压缩。"})
            return
        yield self._session_event("session.message", {"text": "正在压缩上下文…"})
        self._goal_for_active = None
        self._events_for_active = []
        collected: list[EventEnvelope] = []
        for output in self._drive(
            StartRun(
                goal=focus,
                workspace_root=self.workspace,
                model_profile=self.model_profile,
                mode="compact",
                conversation=before,
            ),
            record_conversation=False,
        ):
            if isinstance(output, EventEnvelope):
                collected.append(output)
            yield output
        if self._pending_approval is not None:
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
            self.conversation.replace_with_summary(summary)
            yield self._session_event("session.message", {"text": "上下文压缩完成。"})
            return
        assert self.conversation.snapshot() == before
        yield self._session_event("session.message", {"text": "上下文压缩失败，已保留原上下文。"})

    def _switch_model(self, requested_profile: str | None) -> Iterator[RuntimeOutput]:
        if requested_profile is None:
            yield self._session_event(
                "session.message",
                {"text": f"当前模型：{self.model_profile} / {self._model_name()}"},
            )
            return
        try:
            candidate = self.runtime_builder(self.workspace, requested_profile)
        except Exception as exc:
            yield self._session_event(
                "session.message",
                {"text": f"模型切换失败，已保留当前配置：{exc}"},
            )
            return
        self.dependencies = candidate
        self.model_profile = requested_profile
        self.store = RunStore(candidate.config.state_dir)
        yield self._session_event(
            "session.message",
            {"text": f"已切换模型：{self.model_profile} / {self._model_name()}"},
        )

    def _write_runs(self) -> Iterator[RuntimeOutput]:
        summaries = self.store.list_runs()
        if not summaries:
            yield self._session_event("session.message", {"text": "暂无 run。"})
            return
        lines = [
            f"{summary.run_id}\t{summary.goal_summary}\t{summary.terminal_state or 'active'}"
            for summary in summaries
        ]
        yield self._session_event("session.message", {"text": "\n".join(lines)})

    def _show(self, run_id: str) -> Iterator[RuntimeOutput]:
        events = self.store.read_events(run_id)
        if not events:
            yield self._session_event("session.message", {"text": f"未找到 run：{run_id}"})
            return
        yield from events

    def _rollback(self, run_id: str) -> Iterator[RuntimeOutput]:
        events = tuple(self.dependencies.runtime.handle(RollbackRun(run_id=run_id)))
        if not events:
            yield self._session_event(
                "session.message",
                {"text": f"未找到可回滚的 Checkpoint：{run_id}"},
            )
            return
        yield from events

    def _recover(self, run_id: str | None) -> Iterator[RuntimeOutput]:
        events = tuple(self.dependencies.runtime.handle(InspectRecovery(run_id=run_id)))
        if not events:
            if run_id is None:
                yield self._session_event("session.message", {"text": "暂无待恢复任务。"})
            else:
                yield self._session_event(
                    "session.message",
                    {"text": f"未找到待恢复 run：{run_id}"},
                )
            return
        yield from events

    def _resume(self, run_id: str) -> Iterator[RuntimeOutput]:
        self._goal_for_active = None
        self._events_for_active = []
        outputs = list(self._drive(ResumeRun(run_id=run_id)))
        if not outputs and self._active_run_id is None and self._pending_approval is None:
            yield self._session_event("session.message", {"text": f"未找到可恢复 run：{run_id}"})
            return
        yield from outputs

    def _abandon(self, run_id: str) -> Iterator[RuntimeOutput]:
        events = tuple(self.dependencies.runtime.handle(AbandonRun(run_id=run_id)))
        if not events:
            yield self._session_event("session.message", {"text": f"未找到可放弃 run：{run_id}"})
            return
        yield from events

    def recovery_hint(self) -> EventEnvelope | None:
        reports = self.dependencies.runtime.coordinator.scan()
        if not reports:
            return None
        rank = {
            RecoveryClassification.MANUAL_REQUIRED: 5,
            RecoveryClassification.RECOVERABLE_PARTIAL_APPLY: 4,
            RecoveryClassification.RESUMABLE_VERIFICATION: 3,
            RecoveryClassification.RESUMABLE_APPROVAL: 2,
            RecoveryClassification.LEGACY_NOT_RESUMABLE: 1,
            RecoveryClassification.SAFE_TO_ABANDON: 0,
        }
        highest = max(reports, key=lambda item: rank.get(item.classification, 0))
        return self._session_event(
            "session.message",
            {
                "text": (
                    f"发现 {len(reports)} 个待恢复任务（最高风险：{highest.classification.value}）"
                )
            },
        )

    def bootstrap_events(self) -> tuple[EventEnvelope, ...]:
        events = [self._status_event()]
        hint = self.recovery_hint()
        if hint is not None:
            events.append(hint)
        events.append(self._session_event("session.message", {"text": "输入 /help 查看命令"}))
        return tuple(events)

    def context_warning_event(self) -> EventEnvelope | None:
        if self.conversation.stats().warning:
            return self._session_event(
                "session.message",
                {"text": "上下文已接近上限。可使用 /compact 或 /new。"},
            )
        return None

    def _status_event(self) -> EventEnvelope:
        status = self.status_service.snapshot(
            workspace=self.workspace,
            model_profile=self.model_profile,
            model_name=self._model_name(),
            conversation=self.conversation.stats(),
            permissions=permission_status(self.dependencies.runtime.command_policy),
        )
        return self._session_event("session.status", status.model_dump(mode="json"))

    def _model_name(self) -> str:
        provider = self.dependencies.config.providers.get(self.model_profile)
        if provider is None:
            return "unavailable"
        return provider.model

    def _session_event(self, event_type: str, payload: dict[str, object]) -> EventEnvelope:
        self._session_sequence += 1
        return EventEnvelope(
            event_id=f"session_{uuid4().hex}",
            run_id=self.conversation.stats().session_id,
            sequence=self._session_sequence,
            timestamp=datetime.now(UTC),
            type=event_type,
            payload=payload,
        )

    @staticmethod
    def _help_text() -> str:
        return (
            "会话命令：\n"
            "  /help                 显示帮助\n"
            "  /status               显示会话状态\n"
            "  /context              显示上下文统计\n"
            "  /permissions          显示有效权限边界\n"
            "  /new                  清空上下文并开始新会话\n"
            "  /clear                清空显示与上下文\n"
            "  /compact [focus]      压缩当前上下文\n"
            "  /model [profile]      查看或切换模型\n"
            "  /runs                 列出任务\n"
            "  /show <run-id>         显示任务事件\n"
            "  /rollback <run-id>     安全回滚任务修改\n"
            "  /recover [run-id]      查看待恢复任务\n"
            "  /resume <run-id>       继续可恢复的审批或验证\n"
            "  /abandon <run-id>      放弃无工作区副作用的中断任务\n"
            "  /exit 或 /quit         退出\n"
            "审批输入：approve、reject 或 cancel"
        )
