from datetime import UTC, datetime

import pytest

from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.session.conversation import ConversationContext


def event(
    event_type: str,
    payload: dict[str, object],
    *,
    sequence: int = 1,
    run_id: str = "run_123",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"event_{sequence}",
        run_id=run_id,
        sequence=sequence,
        timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        type=event_type,
        payload=payload,
    )


def test_context_records_conversation_in_order() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")

    context.record_response("Hello", "你好")

    assert context.snapshot() == (
        ConversationMessage(role="user", content="Hello"),
        ConversationMessage(role="assistant", content="你好"),
    )
    assert context.stats().message_count == 2
    assert context.stats().session_id == "session-1"
    assert context.stats().compaction_count == 0


def test_code_run_stores_summary_without_diff_or_tool_output() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")
    events = (
        event("tool.completed", {"name": "read_file", "content": "secret body"}),
        event("changeset.proposed", {"unified_diff": "must-not-be-stored"}, sequence=2),
        event("changeset.applied", {"status": "applied"}, sequence=3),
        event(
            "run.completed",
            {"state": "completed", "outcome": "changed"},
            sequence=4,
        ),
    )

    context.record_run("change color", events)

    serialized = "\n".join(message.content for message in context.snapshot())
    assert "change color" in serialized
    assert "已应用" in serialized
    assert "secret body" not in serialized
    assert "must-not-be-stored" not in serialized


def test_warning_at_seventy_percent_capacity() -> None:
    context = ConversationContext(100, session_id_factory=lambda: "session-1")
    context.record_response("a" * 40, "b" * 30)

    assert context.stats().context_bytes == 70
    assert context.stats().warning is True
    assert context.stats().max_bytes == 100


def test_rejects_input_that_would_exceed_limit() -> None:
    context = ConversationContext(20, session_id_factory=lambda: "session-1")
    context.record_response("hello", "hi")

    assert context.can_accept("x" * 20) is False
    before = context.snapshot()
    with pytest.raises(ValueError, match="capacity exceeded"):
        context.record_response("x" * 20, "y")
    assert context.snapshot() == before


def test_reset_clears_messages_and_changes_session_id() -> None:
    ids = iter(["session-1", "session-2"])
    context = ConversationContext(200_000, session_id_factory=lambda: next(ids))
    context.record_response("Hello", "你好")
    context.replace_with_summary("摘要内容足够长")

    new_id = context.reset()

    assert new_id == "session-2"
    assert context.snapshot() == ()
    assert context.stats().session_id == "session-2"
    assert context.stats().message_count == 0
    assert context.stats().compaction_count == 0


def test_replace_with_summary_is_atomic_and_rejects_empty() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")
    context.record_response("Hello", "你好")
    before = context.snapshot()

    with pytest.raises(ValueError, match="summary must not be empty"):
        context.replace_with_summary("   ")
    assert context.snapshot() == before

    context.replace_with_summary("保留决策：使用 Python。")
    assert context.snapshot() == (
        ConversationMessage(role="summary", content="保留决策：使用 Python。"),
    )
    assert context.stats().compaction_count == 1
    assert context.stats().session_id == "session-1"


def test_failed_and_cancelled_runs_use_deterministic_summaries() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")
    context.record_run(
        "cancel me",
        (
            event("run.started", {"run_id": "run_456"}, run_id="run_456"),
            event("run.cancelled", {"reason": "cancelled_by_user"}, run_id="run_456", sequence=2),
        ),
    )
    context.record_run(
        "fail me",
        (
            event("run.started", {"run_id": "run_789"}, run_id="run_789"),
            event(
                "run.failed",
                {"reason": "model_error"},
                run_id="run_789",
                sequence=2,
            ),
        ),
    )

    contents = [message.content for message in context.snapshot()]
    assert contents == [
        "cancel me",
        "run run_456 已取消，工作区未应用该 Change Set。",
        "fail me",
        "run run_789 失败：model_error。",
    ]


def test_responded_run_stores_assistant_message_text() -> None:
    context = ConversationContext(200_000, session_id_factory=lambda: "session-1")
    context.record_run(
        "Hello",
        (
            event("assistant.message", {"content": "你好"}),
            event(
                "run.completed",
                {"state": "completed", "outcome": "responded"},
                sequence=2,
            ),
        ),
    )

    assert context.snapshot() == (
        ConversationMessage(role="user", content="Hello"),
        ConversationMessage(role="assistant", content="你好"),
    )
