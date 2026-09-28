"""Ephemeral in-process conversation context for Vera sessions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import uuid4

from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import ConversationTurn
from vera.session.models import ConversationStats
from vera.session.turns import ConversationTurnProjector


def _content_bytes(messages: Sequence[ConversationMessage]) -> int:
    return sum(len(message.content.encode("utf-8")) for message in messages)


def _default_session_id() -> str:
    return f"session_{uuid4().hex}"


def _fact_lines(messages: Sequence[ConversationMessage]) -> tuple[str, ...]:
    lines: list[str] = []
    for message in messages:
        for line in message.content.splitlines():
            stripped = line.strip()
            if stripped.startswith("[facts]"):
                lines.append(stripped)
    return tuple(lines)


class ConversationContext:
    """Process-local conversation history with a hard UTF-8 byte budget."""

    def __init__(
        self,
        max_bytes: int,
        session_id_factory: Callable[[], str] | None = None,
        *,
        max_items: int = 200,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        if max_items < 2:
            raise ValueError("max_items must be >= 2")
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._session_id_factory = session_id_factory or _default_session_id
        self._session_id = self._session_id_factory()
        self._messages: list[ConversationMessage] = []
        self._compaction_count = 0

    @classmethod
    def restore(
        cls,
        max_bytes: int,
        *,
        session_id: str,
        messages: Sequence[ConversationMessage],
        compaction_count: int,
        max_items: int = 200,
    ) -> ConversationContext:
        context = cls(max_bytes, session_id_factory=lambda: session_id, max_items=max_items)
        items = list(messages)
        if _content_bytes(items) > max_bytes or len(items) > context._max_items:
            raise ValueError("conversation capacity exceeded")
        context._messages = items
        context._compaction_count = compaction_count
        return context

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
        compacted, _count = self._compacted(candidate)
        return _content_bytes(compacted) <= self._max_bytes

    def record_response(self, user_text: str, assistant_text: str) -> None:
        self.commit_turn(ConversationTurnProjector().from_response(user_text, assistant_text))

    def record_run(self, user_text: str, events: Sequence[EventEnvelope]) -> None:
        self.commit_turn(ConversationTurnProjector().from_run(user_text, events))

    def commit_turn(self, turn: ConversationTurn) -> None:
        self._commit(
            (
                *self._messages,
                ConversationMessage(role="user", content=turn.user_text),
                ConversationMessage(role="assistant", content=turn.assistant_text),
            )
        )

    def summary_with_facts(self, summary: str) -> str:
        text = summary.strip()
        if not text:
            raise ValueError("summary must not be empty")
        facts = _fact_lines(self._messages)
        # A model-written marker is not evidence that the actual facts survived.
        missing = [fact for fact in facts[-8:] if fact not in text.splitlines()]
        if missing:
            text = text + "\n" + "\n".join(missing)
        return text

    def replace_with_summary(self, summary: str) -> None:
        text = self.summary_with_facts(summary)
        self._commit((ConversationMessage(role="summary", content=text),))
        self._compaction_count += 1

    def reset(self) -> str:
        self._messages = []
        self._compaction_count = 0
        self._session_id = self._session_id_factory()
        return self._session_id

    def bind_session_id(self, session_id: str) -> None:
        text = session_id.strip()
        if not text:
            raise ValueError("session_id must not be blank")
        self._session_id = text

    def _compacted(
        self, messages: Sequence[ConversationMessage]
    ) -> tuple[list[ConversationMessage], int]:
        items = list(messages)
        folds = 0
        while (
            items
            and (_content_bytes(items) > self._max_bytes or len(items) > self._max_items)
            and len(items) > 2
        ):
            previous_bytes = _content_bytes(items)
            dropped, kept = items[:-2], items[-2:]
            facts = list(_fact_lines(dropped))[-8:]
            counts = [len(facts), 4, 2, 1, 0]
            nxt: list[ConversationMessage] | None = None
            for fact_count in counts:
                if fact_count <= 0 or not facts:
                    body = "先前轮次已压缩，权威事实见 [facts] 引用。"
                else:
                    body = "\n".join(facts[-min(fact_count, len(facts)) :])
                    if not body.strip():
                        body = "先前轮次已压缩，权威事实见 [facts] 引用。"
                candidate = [ConversationMessage(role="summary", content=body), *kept]
                if _content_bytes(candidate) < previous_bytes or len(candidate) < len(items):
                    nxt = candidate
                    break
            if nxt is None:
                break
            items = nxt
            folds += 1
        return items, folds

    def _commit(self, messages: Sequence[ConversationMessage]) -> None:
        compacted, folds = self._compacted(messages)
        if _content_bytes(compacted) > self._max_bytes:
            raise ValueError("conversation capacity exceeded")
        self._messages = compacted
        self._compaction_count += folds
