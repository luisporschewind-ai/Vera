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
        self._commit(
            (
                *self._messages,
                ConversationMessage(role="user", content=user_text),
                ConversationMessage(role="assistant", content=assistant_text),
            )
        )

    def record_run(self, user_text: str, events: Sequence[EventEnvelope]) -> None:
        assistant_text = self._assistant_from_events(events)
        summary = self._summary_from_events(events)
        has_changeset = any(event.type == "changeset.proposed" for event in events)
        if assistant_text is not None and not has_changeset:
            self.record_response(user_text, assistant_text)
            return
        body = summary
        if assistant_text is not None and assistant_text not in summary:
            body = f"{assistant_text}\n{summary}"
        self._commit(
            (
                *self._messages,
                ConversationMessage(role="user", content=user_text),
                ConversationMessage(role="assistant", content=body),
            )
        )

    def replace_with_summary(self, summary: str) -> None:
        text = summary.strip()
        if not text:
            raise ValueError("summary must not be empty")
        facts = _fact_lines(self._messages)
        if facts and "[facts]" not in text:
            text = text + "\n" + "\n".join(facts[-8:])
        self._commit((ConversationMessage(role="summary", content=text),))
        self._compaction_count += 1

    def reset(self) -> str:
        self._messages = []
        self._compaction_count = 0
        self._session_id = self._session_id_factory()
        return self._session_id

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
    def _fact_block(events: Sequence[EventEnvelope]) -> str:
        run_id = events[0].run_id if events else "unknown"
        parts = [f"run={run_id}"]
        for event in events:
            if event.type == "changeset.proposed":
                changeset_id = event.payload.get("changeset_id", "")
                files = event.payload.get("files") or []
                file_parts: list[str] = []
                if isinstance(files, list):
                    for item in files:
                        if not isinstance(item, dict):
                            continue
                        file_parts.append(f"{item.get('operation')} {item.get('path')}")
                parts.append(f"changeset={changeset_id} files={'; '.join(file_parts)}")
            elif event.type == "approval.required":
                parts.append(f"approval={event.payload.get('approval_id')}")
            elif event.type == "run.failed":
                parts.append(f"error={event.payload.get('reason')}")
            elif event.type in {"recovery.detected", "recovery.manual_required"}:
                parts.append(f"recovery={event.payload.get('classification')}")
        if parts == [f"run={run_id}"]:
            return ""
        return "[facts] " + " ".join(str(part) for part in parts)

    @classmethod
    def _summary_from_events(cls, events: Sequence[EventEnvelope]) -> str:
        run_id = events[0].run_id if events else "unknown"
        human = f"run {run_id} 已结束。"
        for event in events:
            if event.type == "run.cancelled":
                human = f"run {run_id} 已取消，工作区未应用该 Change Set。"
                break
            if event.type == "run.failed":
                reason = event.payload.get("reason", "unknown")
                human = f"run {run_id} 失败：{reason}。"
                break
            if event.type == "run.completed":
                if any(item.type == "changeset.applied" for item in events):
                    human = f"run {run_id} 已应用 Change Set，验证通过。"
                else:
                    outcome = event.payload.get("outcome", "completed")
                    human = f"run {run_id} 已完成（{outcome}）。"
                break
        facts = cls._fact_block(events)
        if facts:
            return f"{human}\n{facts}"
        return human
