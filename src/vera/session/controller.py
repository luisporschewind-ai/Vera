"""UI-independent session controller over VeraRuntime."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vera.bootstrap import RuntimeBuilder, RuntimeDependencies, build_runtime
from vera.contracts.commands import (
    CancelRun,
    ResolveApproval,
    ResumeRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.run_store import RunStore
from vera.persistence.session_store import ConversationSessionStore, LoadedConversationSession
from vera.session.actions import (
    SessionAction,
)
from vera.session.command_flow import SessionCommandFlow
from vera.session.conversation import ConversationContext
from vera.session.editor_flow import SessionEditorFlow
from vera.session.history import PromptHistory
from vera.session.inspection_flow import SessionInspectionFlow
from vera.session.models import ConversationStats, ReasoningStatus, SessionStatus
from vera.session.permissions import permission_status
from vera.session.persistence_flow import SessionPersistenceFlow
from vera.session.run_flow import SessionRunFlow
from vera.session.status import SessionStatusService
from vera.session.turns import ConversationTurnProjector


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
        )

    @property
    def session_source(self) -> Literal["new", "continued", "resumed"]:
        return self._source

    def _apply_loaded_session(
        self, loaded: LoadedConversationSession, *, restore_history: bool
    ) -> None:
        SessionPersistenceFlow.apply_loaded_session(self, loaded, restore_history=restore_history)

    def _bind_persistence(
        self, loaded: LoadedConversationSession, *, restore_history: bool
    ) -> None:
        SessionPersistenceFlow.bind_persistence(self, loaded, restore_history=restore_history)

    def conversation_stats(self) -> ConversationStats:
        return SessionPersistenceFlow.conversation_stats(self)

    def _persistence_code(self, exc: BaseException) -> str:
        return SessionPersistenceFlow.persistence_code(self, exc)

    def _mark_unsaved(self, code: str) -> EventEnvelope:
        return SessionPersistenceFlow.mark_unsaved(self, code)

    def _persist_turn(
        self, user_text: str, events: tuple[EventEnvelope, ...]
    ) -> Iterator[RuntimeOutput]:
        yield from SessionPersistenceFlow.persist_turn(self, user_text, events)

    def _persist_compaction(self, summary: str) -> Iterator[RuntimeOutput]:
        yield from SessionPersistenceFlow.persist_compaction(self, summary)

    def _open_new_persistent_session(self) -> str:
        return SessionPersistenceFlow.open_new_persistent_session(self)

    def mark_active(self, run_id: str) -> None:
        """Test helper: mark a run as active without starting Core."""

        self._active_run_id = run_id

    def dispatch(self, action: SessionAction) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.dispatch(self, action)

    def _submit(self, text: str) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.submit(self, text)

    def _queue_prompt(self, text: str) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.queue_prompt(self, text)

    def _clear_queued_prompt(self) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.clear_queued_prompt(self)

    def _resolve_approval(
        self, approval_id: str, decision: Literal["approve", "reject", "cancel"]
    ) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.resolve_approval(self, approval_id, decision)

    def _cancel(self, run_id: str) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.cancel(self, run_id)

    def _close(self) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.close(self)

    def _drive(
        self,
        command: StartRun | ResolveApproval | CancelRun | ResumeRun,
        *,
        record_conversation: bool = True,
    ) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.drive(self, command, record_conversation=record_conversation)

    def _finish_active_run(self, *, record_conversation: bool = True) -> Iterator[RuntimeOutput]:
        yield from SessionRunFlow.finish_active_run(self, record_conversation=record_conversation)

    def _confirm_editor(self, accept: bool) -> Iterator[RuntimeOutput]:
        yield from SessionEditorFlow.confirm_editor(self, accept)

    def _open_editor(self, text: str) -> Iterator[RuntimeOutput]:
        yield from SessionEditorFlow.open_editor(self, text)

    def _slash(self, raw: str) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.slash(self, raw)

    def _compact(self, focus: str) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.compact(self, focus)

    def _switch_model(self, requested_profile: str | None) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.switch_model(self, requested_profile)

    def _write_runs(self) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.write_runs(self)

    def _show(self, run_id: str) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.show(self, run_id)

    def _rollback(self, run_id: str) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.rollback(self, run_id)

    def _recover(self, run_id: str | None) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.recover(self, run_id)

    def _resume(self, run_id: str) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.resume(self, run_id)

    def _abandon(self, run_id: str) -> Iterator[RuntimeOutput]:
        yield from SessionCommandFlow.abandon(self, run_id)

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
        return SessionCommandFlow.required_run_id_hint(self, handler)

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

    def _cmd_help(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.help(self, args)

    def _cmd_status(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.status(self, args)

    def _cmd_context(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.context(self, args)

    def _cmd_permissions(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.permissions(self, args)

    def _cmd_instructions(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.instructions(self, args)

    def _cmd_init(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.init(self, args)

    def _cmd_sessions(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.sessions(self, args)

    def _cmd_new(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.new(self, args)

    def _cmd_clear(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.clear(self, args)

    def _begin_fresh_session(self, message: str) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.begin_fresh_session(self, message)

    def _cmd_compact(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.compact(self, args)

    def _cmd_model(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.model(self, args)

    def _cmd_runs(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.runs(self, args)

    def _cmd_show(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.show(self, args)

    def _cmd_rollback(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.rollback(self, args)

    def _cmd_recover(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.recover(self, args)

    def _cmd_resume(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.resume(self, args)

    def _cmd_abandon(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.abandon(self, args)

    def _cmd_exit(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.exit(self, args)

    def _cmd_diff(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.diff(self, args)

    def _cmd_review(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.review(self, args)

    def _cmd_doctor(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.doctor(self, args)

    def _cmd_config(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.config(self, args)

    def _cmd_usage(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.usage(self, args)

    def _cmd_shortcuts(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.shortcuts(self, args)

    def _cmd_theme(self, args: tuple[str, ...]) -> Iterator[RuntimeOutput]:
        yield from SessionInspectionFlow.theme(self, args)

    def _help_text(self) -> str:
        return SessionInspectionFlow.help_text(self)
