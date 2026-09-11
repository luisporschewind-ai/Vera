"""Ephemeral in-process conversation context for Vera sessions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import uuid4

from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.session.models import ConversationStats


def _content_bytes(messages: Sequence[ConversationMessage]) -> int:
    return sum(len(message.content.encode("utf-8")) for message in messages)


def _default_session_id() -> str:
    return f"session_{uuid4().hex}"


class ConversationContext:
    """Process-local conversation history with a hard UTF-8 byte budget."""

    def __init__(
        self,
        max_bytes: int,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        self._max_bytes = max_bytes
        self._session_id_factory = session_id_factory or _default_session_id
        self._session_id = self._session_id_factory()
        self._messages: list[ConversationMessage] = []
        self._compaction_count = 0

    def snapshot(self) -> tuple[ConversationMessage, ...]:
        return tuple(self._messages)

    def stats(self) -> ConversationStats:
        used = _content_bytes(self._messages)
        return ConversationStats(
            session_id=self._session_id,
            message_count=len(self._messages),
            context_bytes=used,
            max_bytes=self._max_bytes,
            warning=used * 10 >= self._max_bytes * 7,
            compaction_count=self._compaction_count,
        )

    def can_accept(self, content: str) -> bool:
        candidate = (
            *self._messages,
            ConversationMessage(role="user", content=content),
        )
        return _content_bytes(candidate) <= self._max_bytes

    def record_response(self, user_text: str, assistant_text: str) -> None:
        self._commit(
            (
                *self._messages,
                ConversationMessage(role="user", content=user_text),
                ConversationMessage(role="assistant", content=assistant_text),
            )
        )

    def record_run(self, user_text: str, events: Sequence[EventEnvelope]) -> None:
        assistant_text = self._assistant_from_events(events)
        if assistant_text is not None:
            self.record_response(user_text, assistant_text)
            return
        summary = self._summary_from_events(events)
        self._commit(
            (
                *self._messages,
                ConversationMessage(role="user", content=user_text),
                ConversationMessage(role="assistant", content=summary),
            )
        )

    def replace_with_summary(self, summary: str) -> None:
        text = summary.strip()
        if not text:
            raise ValueError("summary must not be empty")
        self._commit((ConversationMessage(role="summary", content=text),))
        self._compaction_count += 1

    def reset(self) -> str:
        self._messages = []
        self._compaction_count = 0
        self._session_id = self._session_id_factory()
        return self._session_id

    def _commit(self, messages: Sequence[ConversationMessage]) -> None:
        if _content_bytes(messages) > self._max_bytes:
            raise ValueError("conversation capacity exceeded")
        self._messages = list(messages)

    @staticmethod
    def _assistant_from_events(events: Sequence[EventEnvelope]) -> str | None:
        for event in reversed(events):
            if event.type != "assistant.message":
                continue
            content = event.payload.get("content")
            if isinstance(content, str) and content.strip():
                return content
        return None

    @staticmethod
    def _summary_from_events(events: Sequence[EventEnvelope]) -> str:
        run_id = events[0].run_id if events else "unknown"
        for event in events:
            if event.type == "run.cancelled":
                return f"run {run_id} 已取消，工作区未应用该 Change Set。"
            if event.type == "run.failed":
                reason = event.payload.get("reason", "unknown")
                return f"run {run_id} 失败：{reason}。"
            if event.type == "run.completed":
                if any(item.type == "changeset.applied" for item in events):
                    return f"run {run_id} 已应用 Change Set，验证通过。"
                outcome = event.payload.get("outcome", "completed")
                return f"run {run_id} 已完成（{outcome}）。"
        return f"run {run_id} 已结束。"
