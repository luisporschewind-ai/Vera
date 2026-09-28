"""Session persistence and conversation-store flow."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vera.contracts.errors import classify_os_error
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput
from vera.persistence.errors import PersistenceFault
from vera.persistence.session_store import LoadedConversationSession
from vera.session.conversation import ConversationContext
from vera.session.flow_constants import _UNSAVED_ADVICE
from vera.session.models import ConversationStats

if TYPE_CHECKING:
    from vera.session.controller import SessionController


def apply_loaded_session(
    host: SessionController, loaded: LoadedConversationSession, *, restore_history: bool
) -> None:
    if host.dependencies.runtime.access_session is not None:
        host.dependencies.runtime.access_session.reset()
    host.conversation = ConversationContext.restore(
        host.dependencies.config.limits.max_conversation_bytes,
        session_id=loaded.session_id,
        messages=loaded.model_messages,
        compaction_count=loaded.compaction_count,
    )
    host._bind_persistence(loaded, restore_history=restore_history)


def bind_persistence(
    host: SessionController, loaded: LoadedConversationSession, *, restore_history: bool
) -> None:
    host._title = loaded.title
    host._last_saved_sequence = loaded.records[-1].sequence if loaded.records else None
    host._persistence_state = "saved"
    host._last_error_code = None
    if restore_history:
        host.history.clear()
        for message in loaded.history_messages:
            if message.role == "user":
                host.history.record(message.content)


def conversation_stats(host: SessionController) -> ConversationStats:
    return host.conversation.stats().model_copy(
        update={
            "source": host._source,
            "title": host._title,
            "persistent_state": host._persistence_state,
            "last_saved_sequence": host._last_saved_sequence,
            "last_error_code": host._last_error_code,
        }
    )


def persistence_code(host: SessionController, exc: BaseException) -> str:
    if isinstance(exc, PersistenceFault):
        return exc.code
    return classify_os_error(exc)


def mark_unsaved(host: SessionController, code: str) -> EventEnvelope:
    host._persistence_state = "unsaved"
    host._last_error_code = code
    return host._session_event(
        "session.persistence_changed",
        {"state": "unsaved", "error_code": code, "advice": _UNSAVED_ADVICE},
    )


def persist_turn(
    host: SessionController, user_text: str, events: tuple[EventEnvelope, ...]
) -> Iterator[RuntimeOutput]:
    turn = host.turn_projector.from_run(user_text, events)
    session_id = host.conversation.stats().session_id
    try:
        record = host.session_store.append_turn(session_id, turn)
    except Exception as exc:
        host.conversation.commit_turn(turn)
        yield host._mark_unsaved(host._persistence_code(exc))
        return
    host.conversation.commit_turn(turn)
    if host._persistence_state != "unsaved":
        host._last_saved_sequence = record.sequence
        host._title = host.session_store.load(session_id, host.workspace).title
        host._last_error_code = None


def persist_compaction(host: SessionController, summary: str) -> Iterator[RuntimeOutput]:
    summary = host.conversation.summary_with_facts(summary)
    session_id = host.conversation.stats().session_id
    through = host._last_saved_sequence or 1
    try:
        record = host.session_store.append_compaction(session_id, summary, through)
    except Exception as exc:
        yield host._mark_unsaved(host._persistence_code(exc))
        return
    host.conversation.replace_with_summary(summary)
    if host._persistence_state != "unsaved":
        host._last_saved_sequence = record.sequence
        host._last_error_code = None
    yield host._session_event("session.message", {"text": "上下文压缩完成。"})


def open_new_persistent_session(host: SessionController) -> str:
    loaded = host.session_store.create(host.workspace)
    host._source = "new"
    host._apply_loaded_session(loaded, restore_history=True)
    host.queued_prompt = None
    host._run_guidance_hash = None
    return loaded.session_id


class SessionPersistenceFlow:
    """Stable façade for conversation persistence operations."""

    apply_loaded_session = staticmethod(apply_loaded_session)
    bind_persistence = staticmethod(bind_persistence)
    conversation_stats = staticmethod(conversation_stats)
    persistence_code = staticmethod(persistence_code)
    mark_unsaved = staticmethod(mark_unsaved)
    persist_turn = staticmethod(persist_turn)
    persist_compaction = staticmethod(persist_compaction)
    open_new_persistent_session = staticmethod(open_new_persistent_session)
