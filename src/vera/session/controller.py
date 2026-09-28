"""UI-independent session controller over VeraRuntime."""

from __future__ import annotations

import shlex
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vera.bootstrap import RuntimeBuilder, RuntimeDependencies, build_runtime
from vera.config import ConfigurationError
from vera.contracts.commands import (
    AbandonRun,
    CancelRun,
    InspectRecovery,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.errors import classify_os_error
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification
from vera.contracts.skills import SkillSelection, SkillSnapshot
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.errors import PersistenceFault
from vera.persistence.run_store import RunStore
from vera.persistence.session_store import ConversationSessionStore, LoadedConversationSession
from vera.persistence.workspace_permissions import (
    WorkspacePermissionStore,
    WorkspacePermissionStoreError,
)
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.project_instructions import (
    format_instruction_status,
    public_instruction_facts,
)
from vera.runtime.prompts import PROJECT_INIT_GOAL
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    ResolveSessionApproval,
    SessionAction,
    SubmitPrompt,
)
from vera.session.conversation import ConversationContext
from vera.session.external_editor import ExternalEditor, ExternalEditorError
from vera.session.history import PromptHistory
from vera.session.models import ConversationStats, ReasoningStatus, SessionStatus
from vera.session.permissions import permission_status
from vera.session.status import SessionStatusService
from vera.session.turns import ConversationTurnProjector
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService

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

_UNSAVED_ADVICE = (
    "会话记录写入失败。工作区与 Run 证据已保留；当前进程可继续使用本轮，"
    "但退出前请新建会话或从已保存前缀恢复。"
)


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str
    active_run_id: str | None
    pending_approval_id: str | None
    model_profile: str
    closed: bool
    skill_selection: SkillSelection = field(default_factory=SkillSelection)


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
        session_store: ConversationSessionStore | None = None,
        loaded_session: LoadedConversationSession | None = None,
        source: Literal["new", "continued", "resumed"] | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.workspace = workspace.resolve()
        self.model_profile = model_profile
        self.store = RunStore(dependencies.config.state_dir)
        self.session_store = session_store or ConversationSessionStore(
            dependencies.config.state_dir,
            dependencies.installation_id,
        )
        self.turn_projector = ConversationTurnProjector()
        self.status_service = status_service or SessionStatusService()
        self.runtime_builder = runtime_builder or build_runtime
        self._active_run_id: str | None = None
        self._drive_epoch = 0
        self._pending_approval: EventEnvelope | None = None
        self._closed = False
        self._session_sequence = 0
        self._goal_for_active: str | None = None
        self._events_for_active: list[EventEnvelope] = []
        self.clear_display_requested = False
        self.exit_requested = False
        self.history = PromptHistory()
        self.queued_prompt: str | None = None
        self._editor_confirmed = False
        self._editor_draft: Path | None = None
        self.theme = "default"
        self._persistence_state: Literal["saved", "unsaved"] = "saved"
        self._last_error_code: str | None = None
        self._title = "新会话"
        self._last_saved_sequence: int | None = None
        self._source: Literal["new", "continued", "resumed"] = source or "new"
        self._run_guidance_hash: str | None = None
        if loaded_session is None:
            loaded_session = self.session_store.create(self.workspace)
            self._source = source or "new"
            if conversation is not None:
                conversation.bind_session_id(loaded_session.session_id)
                self.conversation = conversation
                self._bind_persistence(loaded_session, restore_history=False)
                return
        else:
            self._source = source or "resumed"
        self._apply_loaded_session(loaded_session, restore_history=True)

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
            skill_selection=self._skill_selection(),
        )

    def _skill_selection(self) -> SkillSelection:
        service = getattr(self.dependencies.runtime, "skill_selection_service", None)
        return service.pending if service is not None else SkillSelection()

    def _active_skill_snapshot(self) -> SkillSnapshot | None:
        if self._active_run_id is None:
            return None
        context = self.dependencies.runtime.runs.get(self._active_run_id)
        return context.skill_snapshot if context is not None else None

    @property
    def session_source(self) -> Literal["new", "continued", "resumed"]:
        return self._source

    def _apply_loaded_session(
        self, loaded: LoadedConversationSession, *, restore_history: bool
    ) -> None:
        self.conversation = ConversationContext.restore(
            self.dependencies.config.limits.max_conversation_bytes,
            session_id=loaded.session_id,
            messages=loaded.model_messages,
            compaction_count=loaded.compaction_count,
        )
        self._bind_persistence(loaded, restore_history=restore_history)
        self._skill_service().restore(loaded.skill_selection)

    def _persist_skill_selection(self, selection: SkillSelection) -> Iterator[RuntimeOutput]:
        try:
            record = self.session_store.append_skill_selection(
                self.conversation.stats().session_id, selection
            )
        except Exception as exc:
            yield self._mark_unsaved(self._persistence_code(exc))
            return
        if self._persistence_state != "unsaved":
            self._last_saved_sequence = record.sequence
            self._last_error_code = None

    def _bind_persistence(
        self, loaded: LoadedConversationSession, *, restore_history: bool
    ) -> None:
        self._title = loaded.title
        self._last_saved_sequence = loaded.records[-1].sequence if loaded.records else None
        self._persistence_state = "saved"
        self._last_error_code = None
        if restore_history:
            self.history.clear()
            for message in loaded.history_messages:
                if message.role == "user":
                    self.history.record(message.content)

    def conversation_stats(self) -> ConversationStats:
        return self.conversation.stats().model_copy(
            update={
                "source": self._source,
                "title": self._title,
                "persistent_state": self._persistence_state,
                "last_saved_sequence": self._last_saved_sequence,
                "last_error_code": self._last_error_code,
            }
        )

    def _persistence_code(self, exc: BaseException) -> str:
        if isinstance(exc, PersistenceFault):
            return exc.code
        return classify_os_error(exc)

    def _mark_unsaved(self, code: str) -> EventEnvelope:
        self._persistence_state = "unsaved"
        self._last_error_code = code
        return self._session_event(
            "session.persistence_changed",
            {"state": "unsaved", "error_code": code, "advice": _UNSAVED_ADVICE},
        )

    def _persist_turn(
        self, user_text: str, events: tuple[EventEnvelope, ...]
    ) -> Iterator[RuntimeOutput]:
        turn = self.turn_projector.from_run(user_text, events)
        session_id = self.conversation.stats().session_id
        try:
            record = self.session_store.append_turn(session_id, turn)
        except Exception as exc:
            self.conversation.commit_turn(turn)
            yield self._mark_unsaved(self._persistence_code(exc))
            return
        self.conversation.commit_turn(turn)
        if self._persistence_state != "unsaved":
            self._last_saved_sequence = record.sequence
            self._title = self.session_store.load(session_id, self.workspace).title
            self._last_error_code = None

    def _persist_compaction(self, summary: str) -> Iterator[RuntimeOutput]:
        session_id = self.conversation.stats().session_id
        through = self._last_saved_sequence or 1
        try:
            record = self.session_store.append_compaction(session_id, summary, through)
        except Exception as exc:
            yield self._mark_unsaved(self._persistence_code(exc))
            return
        self.conversation.replace_with_summary(summary)
        if self._persistence_state != "unsaved":
            self._last_saved_sequence = record.sequence
            self._last_error_code = None
        yield self._session_event("session.message", {"text": "上下文压缩完成。"})

    def _open_new_persistent_session(self) -> str:
        loaded = self.session_store.create(self.workspace)
        self._source = "new"
        self._apply_loaded_session(loaded, restore_history=True)
        self.queued_prompt = None
        self._run_guidance_hash = None
        return loaded.session_id

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
                self.history.record(text)
                yield from self._submit(text)
            case ExecuteSlashCommand(raw=raw):
                yield from self._slash(raw)
            case ResolveSessionApproval(approval_id=approval_id, decision=decision):
                yield from self._resolve_approval(approval_id, decision)
            case CancelActiveRun(run_id=run_id):
                yield from self._cancel(run_id)
            case CloseSession():
                yield from self._close()
            case QueuePrompt(text=text):
                yield from self._queue_prompt(text)
            case ClearQueuedPrompt():
                yield from self._clear_queued_prompt()
            case ConfirmExternalEditor(accept=accept):
                yield from self._confirm_editor(accept)
            case OpenExternalEditor(text=text):
                yield from self._open_editor(text)

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
        yield self._session_event("session.user_prompt", {"text": text})
        yield from self._drive(command)

    def _queue_prompt(self, text: str) -> Iterator[RuntimeOutput]:
        if self._pending_approval is not None:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "approval_pending", "message": "等待审批时不能排队下一条输入。"},
            )
            return
        if self._active_run_id is None:
            self.history.record(text)
            yield from self._submit(text)
            return
        if self.queued_prompt is not None:
            yield self._session_event(
                "session.action_rejected",
                {
                    "reason_code": "queue_occupied",
                    "message": "已有一条排队输入，请先撤销再替换。",
                    "queued": True,
                },
            )
            return
        self.queued_prompt = text
        self.history.record(text)
        yield self._session_event("session.prompt_queued", {"queued": True})

    def _clear_queued_prompt(self) -> Iterator[RuntimeOutput]:
        if self.queued_prompt is None:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "queue_empty", "message": "当前没有排队输入。"},
            )
            return
        self.queued_prompt = None
        yield self._session_event("session.prompt_queue_cleared", {"queued": False})

    def _confirm_editor(self, accept: bool) -> Iterator[RuntimeOutput]:
        self._editor_confirmed = accept
        yield self._session_event(
            "session.editor_confirmed" if accept else "session.editor_declined",
            {"accepted": accept},
        )

    def _open_editor(self, text: str) -> Iterator[RuntimeOutput]:
        argv = tuple(getattr(self.dependencies.config, "editor_argv", ()) or ())
        try:
            editor = ExternalEditor(argv, self.dependencies.config.state_dir / "drafts")
        except ExternalEditorError as exc:
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": exc.code, "message": str(exc)},
            )
            return
        preview = editor.preview()
        if not self._editor_confirmed:
            yield self._session_event(
                "session.editor_preview",
                {"argv": list(preview), "needs_confirmation": True},
            )
            return
        path = editor.write_draft(text)
        self._editor_draft = path
        try:
            result = editor.run(path)
        except ExternalEditorError as exc:
            editor.cleanup(path)
            self._editor_draft = None
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": exc.code, "message": str(exc)},
            )
            return
        editor.cleanup(path)
        self._editor_draft = None
        yield self._session_event(
            "session.editor_closed",
            {"status": result.status, "changed": result.changed, "text": result.text},
        )

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
        self.queued_prompt = None
        if self._pending_approval is not None and self._active_run_id is not None:
            approval_id = str(self._pending_approval.payload.get("approval_id", ""))
            yield from self._resolve_approval(approval_id, "cancel")
        if self._active_run_id is not None:
            yield from self._cancel(self._active_run_id)
        if self._persistence_state == "unsaved":
            yield self._session_event(
                "session.close_warning",
                {
                    "state": "unsaved",
                    "error_code": self._last_error_code or "write_failed",
                    "advice": _UNSAVED_ADVICE,
                },
            )
        else:
            try:
                record = self.session_store.close(
                    self.conversation.stats().session_id, "user_close"
                )
                self._last_saved_sequence = record.sequence
            except Exception as exc:
                yield self._mark_unsaved(self._persistence_code(exc))
                yield self._session_event(
                    "session.close_warning",
                    {
                        "state": "unsaved",
                        "error_code": self._last_error_code or "write_failed",
                        "advice": _UNSAVED_ADVICE,
                    },
                )
        self._closed = True
        self.exit_requested = True
        self.history.clear()
        self.queued_prompt = None
        yield self._session_event("session.closed", {"reason": "user_close"})

    def _drive(
        self,
        command: StartRun | ResolveApproval | CancelRun | ResumeRun,
        *,
        record_conversation: bool = True,
    ) -> Iterator[RuntimeOutput]:
        produced_terminal = False
        epoch = self._drive_epoch
        for output in self.dependencies.runtime.stream(command):
            if self._drive_epoch != epoch:
                return
            if isinstance(output, EventEnvelope):
                self._events_for_active.append(output)
                if output.type == "run.started" or (
                    self._active_run_id is None and output.type not in _TERMINAL_TYPES
                ):
                    self._active_run_id = output.run_id
                if output.type == "project.instructions.loaded":
                    digest = output.payload.get("guidance_hash")
                    self._run_guidance_hash = digest if isinstance(digest, str) else None
                if output.type == "approval.required":
                    self._active_run_id = output.run_id
                    self._pending_approval = output
                    yield output
                    return
                if output.type in _TERMINAL_TYPES:
                    produced_terminal = True
            if isinstance(output, EventEnvelope) and output.type == "skill.snapshot.bound":
                selection = self._skill_selection()
                yield from self._persist_skill_selection(selection)
                yield output
                yield self._session_event(
                    "skill.selection.changed",
                    {
                        "selection": selection.model_dump(mode="json"),
                        "text": "Skill 已绑定当前 Run，下一次 Run 未选择 Skill。",
                    },
                )
            else:
                yield output
        if self._drive_epoch != epoch:
            return
        if produced_terminal or self._pending_approval is None:
            yield from self._finish_active_run(record_conversation=record_conversation)
            queued = self.queued_prompt
            if queued and self._active_run_id is None and not self._closed:
                self.queued_prompt = None
                yield self._session_event("session.prompt_queue_flushed", {"queued": True})
                yield from self._submit(queued)

    def _finish_active_run(self, *, record_conversation: bool = True) -> Iterator[RuntimeOutput]:
        self._drive_epoch += 1
        goal = self._goal_for_active
        events = tuple(self._events_for_active)
        self._active_run_id = None
        self._pending_approval = None
        self._goal_for_active = None
        self._events_for_active = []
        if record_conversation and goal is not None and events:
            yield from self._persist_turn(goal, events)

    def _slash(self, raw: str) -> Iterator[RuntimeOutput]:
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            yield self._session_event("session.message", {"text": f"命令格式错误：{exc}"})
            return
        if not parts:
            return
        if (
            self._active_run_id is not None
            and self._pending_approval is None
            and parts[0] != "/trace"
        ):
            yield self._session_event(
                "session.action_rejected",
                {"reason_code": "run_active", "message": "当前有运行中的任务。"},
            )
            return
        from vera.session.command_catalog import CommandCatalog

        catalog = CommandCatalog()
        parsed = catalog.parse(parts)
        if parsed.unknown:
            hint = f" 候选：{', '.join(parsed.suggestions)}。" if parsed.suggestions else ""
            yield self._session_event(
                "session.message",
                {
                    "text": f"未知命令：{parsed.name}。{hint}输入 /help 查看可用命令。",
                    "suggestions": list(parsed.suggestions),
                },
            )
            return
        descriptor = catalog.get(parsed.name)
        if descriptor is not None and descriptor.args == "none" and parsed.args:
            yield self._session_event("session.message", {"text": f"用法：{descriptor.usage}"})
            return
        if descriptor is not None and descriptor.args == "required" and not parsed.args:
            text = f"用法：{descriptor.usage}"
            hint = self._required_run_id_hint(parsed.handler)
            if hint:
                text = f"{text}\n{hint}"
            yield self._session_event("session.message", {"text": text})
            return
        if (
            descriptor is not None
            and descriptor.args == "optional"
            and parsed.handler not in {"compact", "skills"}
            and len(parsed.args) > 1
        ):
            yield self._session_event("session.message", {"text": f"用法：{descriptor.usage}"})
            return
        handler = getattr(self, f"_cmd_{parsed.handler}", None)
        if handler is None:
            yield self._session_event(
                "session.message",
                {"text": f"未知命令：{parsed.name}。输入 /help 查看可用命令。"},
            )
            return
        yield from handler(parsed.args)

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
            yield from self._persist_compaction(summary)
            return
        assert self.conversation.snapshot() == before
        yield self._session_event("session.message", {"text": "上下文压缩失败，已保留原上下文。"})

    def _switch_model(self, requested_profile: str | None) -> Iterator[RuntimeOutput]:
        if requested_profile is None:
            configured = self.dependencies.config.enabled_model_profiles
            if configured:
                from vera.provider_configuration import ProviderConfigurationService

                try:
                    summaries = ProviderConfigurationService().list_profiles_with_keys(
                        self.dependencies.config.providers
                    )
                    candidates = [
                        item.profile_id
                        for item in summaries
                        if item.enabled and item.valid and item.key_status != "missing"
                    ]
                except ConfigurationError:
                    candidates = []
            else:
                candidates = list(self.dependencies.config.providers)
            available = ", ".join(candidates) if candidates else "请先运行 vera models setup"
            yield self._session_event(
                "session.message",
                {
                    "text": f"当前模型：{self.model_profile} / {self._model_name()}\n"
                    f"可用模型：{available}"
                },
            )
            return
        try:
            candidate = self.runtime_builder(self.workspace, requested_profile)
        except Exception as exc:
            reason = exc.code if isinstance(exc, ConfigurationError) else "configuration_failed"
            yield self._session_event(
                "session.message",
                {"text": f"模型切换失败，已保留当前配置：{reason}"},
            )
            return
        candidate.runtime.skill_selection_service = self._skill_service()
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
                    f"发现 {len(reports)} 个待恢复任务"
                    f"（最高风险：{highest.classification.value}）。"
                    "使用 /recover 查看 run-id 后再 /resume 或 /abandon。"
                )
            },
        )

    def _required_run_id_hint(self, handler: str) -> str:
        if handler not in {"abandon", "resume"}:
            return ""
        reports = self.dependencies.runtime.coordinator.scan()
        matching = [item for item in reports if handler in item.allowed_actions]
        if matching:
            lines = [f"可 {handler}："]
            lines.extend(f"{item.run_id}（{item.classification.value}）" for item in matching)
            return "\n".join(lines)
        if reports:
            return f"当前没有可 {handler} 的待恢复任务。使用 /recover 查看需要人工处理的 run。"
        return "当前没有待恢复任务。"

    def bootstrap_events(self) -> tuple[EventEnvelope, ...]:
        events = [self._status_event()]
        if self._source in {"continued", "resumed"}:
            events.append(self._loaded_event())
        hint = self.recovery_hint()
        if hint is not None:
            events.append(hint)
        events.append(self._session_event("session.message", {"text": "输入 /help 查看命令"}))
        return tuple(events)

    def _loaded_event(self) -> EventEnvelope:
        from vera.session.startup import HISTORY_DISPLAY_LIMIT

        items = [
            {"role": message.role, "content": message.content}
            for message in self.conversation.snapshot()[-HISTORY_DISPLAY_LIMIT:]
        ]
        stats = self.conversation_stats()
        return self._session_event(
            "session.loaded",
            {
                "session_id": stats.session_id,
                "source": stats.source,
                "title": stats.title,
                "message_count": stats.message_count,
                "items": items,
            },
        )

    def context_warning_event(self) -> EventEnvelope | None:
        if self.conversation.stats().warning:
            return self._session_event(
                "session.message",
                {"text": "上下文已接近上限。可使用 /compact 或 /new。"},
            )
        return None

    def session_status(self) -> SessionStatus:
        return self.status_service.snapshot(
            workspace=self.workspace,
            model_profile=self.model_profile,
            model_name=self._model_name(),
            conversation=self.conversation_stats(),
            permissions=permission_status(
                self.dependencies.runtime.command_policy,
                workspace_permissions=self.dependencies.runtime.workspace_permissions,
            ),
            reasoning=self._reasoning_status(),
            skill_selection=self._skill_selection(),
            active_skill_snapshot=self._active_skill_snapshot(),
        )

    def _status_event(self) -> EventEnvelope:
        return self._session_event("session.status", self.session_status().model_dump(mode="json"))

    def _reasoning_status(self) -> ReasoningStatus:
        capabilities = getattr(self.dependencies.runtime.adapter, "capabilities", None)
        mode = getattr(capabilities, "reasoning", "unavailable")
        if mode == "provider_default":
            return ReasoningStatus(mode="provider_default")
        return ReasoningStatus(mode="unavailable")

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

    def _events_for_run(self, run_id: str | None) -> tuple[EventEnvelope, ...]:
        from vera.session.queries import load_run_events

        events = load_run_events(self.store, run_id) if run_id else ()
        if not events and run_id is not None and run_id == self._active_run_id:
            events = tuple(self._events_for_active)
        return events

    def _cmd_help(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield self._session_event("session.help", {"text": self._help_text()})

    def _cmd_status(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield self._status_event()

    def _skill_service(self) -> SkillSelectionService:
        service = getattr(self.dependencies.runtime, "skill_selection_service", None)
        if service is None:
            service = SkillSelectionService(SkillRegistry(SkillDiscovery()))
            self.dependencies.runtime.skill_selection_service = service
        return service

    @staticmethod
    def _skill_summary_text(summaries: list[dict[str, object]]) -> str:
        if not summaries:
            return "没有发现 Skill。"
        lines = ["Skills："]
        for item in summaries:
            name = item.get("name") or item.get("skill_id") or "未命名"
            source = item.get("source_kind", "unknown")
            availability = item.get("availability", "unknown")
            version = item.get("version") or "-"
            lines.append(f"- {name} [{source}] {version} · {availability}")
        return "\n".join(lines)

    def _cmd_skills(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        service = self._skill_service()
        operation = args[0] if args else "list"
        selector = args[1] if len(args) > 1 else None
        if operation == "list":
            summaries = [
                item.model_dump(mode="json") for item in service.registry.summaries(self.workspace)
            ]
            yield self._session_event(
                "skill.listed",
                {"items": summaries, "text": self._skill_summary_text(summaries)},
            )
            return
        if operation == "clear" and len(args) == 1:
            selection = service.clear()
            yield from self._persist_skill_selection(selection)
            yield self._session_event(
                "skill.selection.changed",
                {
                    "selection": selection.model_dump(mode="json"),
                    "text": "已清除下一次 Run 的 Skill 选择。",
                },
            )
            return
        if operation not in {"show", "use"} or selector is None or len(args) != 2:
            yield self._session_event(
                "session.action_rejected",
                {
                    "reason_code": "invalid_skill_command",
                    "message": (
                        "用法：/skills、/skills show <name|skill_id>、/skills use "
                        "<name|skill_id> 或 /skills clear"
                    ),
                },
            )
            return
        if operation == "use":
            selection = service.select(selector, self.workspace)
            yield from self._persist_skill_selection(selection)
            text = (
                f"已选择 {selection.skill_id}，只对下一次 Run 生效。"
                if selection.status == "selected" and selection.skill_id
                else (
                    "Skill 选择失败："
                    f"{selection.reason_codes[0] if selection.reason_codes else 'unknown'}"
                )
            )
            yield self._session_event(
                "skill.selection.changed",
                {"selection": selection.model_dump(mode="json"), "text": text},
            )
            return
        selection = service.registry.resolve(selector, self.workspace)
        matches = [
            item
            for item in service.registry.summaries(self.workspace)
            if item.skill_id == selector or item.name == selector
        ]
        dumped = [item.model_dump(mode="json") for item in matches]
        payload: dict[str, object] = {
            "items": dumped,
            "text": self._skill_summary_text(dumped),
        }
        if selection.status == "selected":
            candidate = service.package_for(selection, self.workspace)
            if candidate is not None and candidate.package is not None:
                package = candidate.package
                payload["manifest"] = {
                    "name": package.manifest.name,
                    "version": package.manifest.version,
                    "description": package.manifest.description,
                    "compatibility": package.manifest.compatibility.model_dump(mode="json"),
                }
                payload["resources"] = [
                    {
                        "path": item.relative_path,
                        "kind": item.kind,
                        "byte_count": len(item.content),
                        "content_hash": item.content_hash,
                    }
                    for item in package.files
                ]
        yield self._session_event("skill.shown", payload)

    def _cmd_context(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        stats = self.conversation_stats()
        yield self._session_event(
            "session.context",
            stats.model_dump(mode="json"),
        )

    def _cmd_permissions(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        if args:
            requested = args[0].casefold()
            current = self.dependencies.runtime.workspace_permissions
            if current is None:
                yield self._session_event(
                    "session.action_rejected",
                    {
                        "reason_code": "permissions_unavailable",
                        "message": "当前没有工作区权限快照。",
                    },
                )
                return
            if requested not in {"trust", "revoke"}:
                yield self._session_event(
                    "session.message",
                    {"text": "用法：/permissions [trust|revoke]"},
                )
                return
            snapshot = self.dependencies.runtime.policy_engine.snapshot
            if not isinstance(snapshot, EffectivePolicySnapshotV2):
                yield self._session_event(
                    "session.action_rejected",
                    {
                        "reason_code": "permissions_unavailable",
                        "message": "当前策略版本不支持工作区权限持久化。",
                    },
                )
                return
            store = WorkspacePermissionStore(
                self.dependencies.config.state_dir,
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
                yield self._session_event(
                    "session.action_rejected",
                    {
                        "reason_code": exc.code,
                        "message": "工作区权限状态未更新，请检查私有状态目录。",
                    },
                )
                return
            self.dependencies.runtime.workspace_permissions = updated
        status = permission_status(
            self.dependencies.runtime.command_policy,
            workspace_permissions=self.dependencies.runtime.workspace_permissions,
        )
        yield self._session_event("session.permissions", status.model_dump(mode="json"))

    def _cmd_instructions(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        loaded = self.dependencies.project_instructions.load(self.workspace)
        facts = public_instruction_facts(loaded)
        pending = (
            self._run_guidance_hash is not None and self._run_guidance_hash != loaded.guidance_hash
        )
        payload: dict[str, object] = {
            **facts,
            "run_guidance_hash": self._run_guidance_hash,
            "not_found": not loaded.sources and not loaded.issues,
            "pending_next_run": pending,
        }
        payload["text"] = format_instruction_status(payload)
        yield self._session_event("project.instructions.status", payload)

    def _cmd_init(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        if self._active_run_id is not None:
            pending = self._pending_approval is not None
            yield self._session_event(
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
            workspace_root=self.workspace,
            model_profile=self.model_profile,
            conversation=self.conversation.snapshot(),
            mode="project_init",
        )
        self._goal_for_active = PROJECT_INIT_GOAL
        self._events_for_active = []
        yield from self._drive(command)

    def _cmd_sessions(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        summaries = self.session_store.list_for_workspace(self.workspace)
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
        yield self._session_event(
            "session.listed",
            {"items": items, "text": "\n".join(lines)},
        )

    def _cmd_new(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._begin_fresh_session("已开始新会话：{session_id}")

    def _cmd_clear(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._begin_fresh_session("已清空显示并开始新会话：{session_id}")

    def _begin_fresh_session(self, message: str) -> Iterator[RuntimeOutput]:
        session_id = self._open_new_persistent_session()
        self.clear_display_requested = True
        yield self._session_event(
            "session.message",
            {
                "clear_display": True,
                "text": message.format(session_id=session_id),
            },
        )

    def _cmd_compact(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._compact(" ".join(args) if args else "保留关键结论与未完成事项")

    def _cmd_model(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._switch_model(args[0] if args else None)

    def _cmd_runs(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._write_runs()

    def _cmd_show(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._show(args[0])

    def _cmd_rollback(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._rollback(args[0])

    def _cmd_recover(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._recover(args[0] if args else None)

    def _cmd_resume(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._resume(args[0])

    def _cmd_abandon(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._abandon(args[0])

    def _cmd_exit(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from self._close()

    def _cmd_diff(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        from vera.session.queries import collect_diffs, resolve_run_id

        run_id = resolve_run_id(self.store, args[0] if args else None, self._active_run_id)
        events = self._events_for_run(run_id)
        files = collect_diffs(events)
        applied = any(event.type == "changeset.applied" for event in events)
        if not files:
            yield self._session_event(
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
        yield self._session_event(
            "session.diff",
            {"run_id": run_id, "files": list(files), "applied": applied, "text": body},
        )

    def _cmd_review(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        from vera.presentation.review import project_review
        from vera.session.queries import resolve_run_id

        run_id = resolve_run_id(self.store, args[0] if args else None, self._active_run_id)
        events = self._events_for_run(run_id)
        review = project_review(events)
        review["run_id"] = run_id
        yield self._session_event("session.review", review)

    def _cmd_trace(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        from vera.trace.formatting import format_run_trace
        from vera.trace.projector import trace_snapshot

        requested_id = args[0] if args else None
        runs = tuple(
            summary
            for summary in self.store.list_runs()
            if summary.workspace_root.expanduser().resolve() == self.workspace
        )
        if requested_id is not None:
            selected = next((item for item in runs if item.run_id == requested_id), None)
        elif self.active_run_id is not None:
            selected = next((item for item in runs if item.run_id == self.active_run_id), None)
        else:
            selected = runs[0] if runs else None

        if selected is None:
            message = (
                "未找到属于当前工作区的 Run。"
                if requested_id is None and self.active_run_id is None
                else "未找到属于当前工作区的指定 Run。"
            )
            yield self._session_event("session.message", {"text": message})
            return

        trace = trace_snapshot(
            self.store,
            selected.run_id,
            session_id=self.conversation.stats().session_id,
            installation_id=self.dependencies.installation_id,
        )
        yield self._session_event(
            "session.trace",
            {
                "trace": trace.model_dump(mode="json"),
                "text": format_run_trace(trace),
            },
        )

    def _cmd_doctor(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        import os
        from pathlib import Path as ConfigPath

        from platformdirs import user_config_path

        from vera.session.diagnostics import doctor_report

        user_config = ConfigPath(
            os.environ.get("VERA_USER_CONFIG_FILE", str(user_config_path("Vera") / "config.toml"))
        )
        report = doctor_report(
            workspace=self.workspace,
            state_dir=self.dependencies.config.state_dir,
            user_config=user_config,
        )
        yield self._session_event("session.doctor", report)

    def _cmd_config(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
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
        project_file = self.workspace / ".vera" / "config.toml"
        sources = {
            "user": str(user_file) if user_file.is_file() else "absent",
            "project": str(project_file) if project_file.is_file() else "absent",
            "environment": "applied",
            "cli": "overrides",
        }
        yield self._session_event(
            "session.config",
            redacted_config_view(self.dependencies.config, sources),
        )

    def _cmd_usage(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        from vera.session.queries import usage_snapshot

        selected = self.active_run_id
        if selected is None:
            selected = next(
                (
                    summary.run_id
                    for summary in self.store.list_runs()
                    if summary.workspace_root.resolve() == self.workspace.resolve()
                ),
                None,
            )
        events = self._events_for_run(selected)
        yield self._session_event("session.usage", usage_snapshot(events))

    def _cmd_shortcuts(self, _args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        from vera.session.diagnostics import shortcut_list

        items = shortcut_list()
        text = "\n".join(f"{item['keys']}\t{item['action']}" for item in items)
        yield self._session_event(
            "session.shortcuts",
            {"items": [dict(item) for item in items], "text": text},
        )

    def _cmd_theme(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        from vera.terminal.theme import THEME_NAMES, format_theme_status, normalize_theme

        if not args:
            yield self._session_event(
                "session.theme",
                {
                    "theme": self.theme,
                    "available": list(THEME_NAMES),
                    "text": format_theme_status(self.theme),
                },
            )
            return
        selected = normalize_theme(args[0], self.theme)  # type: ignore[arg-type]
        if selected is None:
            yield self._session_event(
                "session.message",
                {"text": f"未知主题：{args[0]}。可用：{', '.join(THEME_NAMES)}"},
            )
            return
        self.theme = selected
        yield self._session_event(
            "session.theme",
            {
                "theme": self.theme,
                "available": list(THEME_NAMES),
                "text": format_theme_status(self.theme),
            },
        )

    def _help_text(self) -> str:
        from vera.session.command_catalog import CommandCatalog

        return CommandCatalog().help_text(self.snapshot())
