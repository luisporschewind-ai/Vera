from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import ConversationTurn
from vera.session.turns import ConversationTurnProjector


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


def serialized(turn: ConversationTurn) -> str:
    return turn.model_dump_json()


def test_from_response_is_plain_conversation_turn() -> None:
    turn = ConversationTurnProjector().from_response("Hello", "你好")
    assert turn == ConversationTurn(
        user_text="Hello",
        assistant_text="你好",
        run_id=None,
        terminal_state="response",
    )


def test_from_run_keeps_assistant_text_without_changeset() -> None:
    turn = ConversationTurnProjector().from_run(
        "Hello",
        (
            event("assistant.message", {"content": "你好"}),
            event("run.completed", {"state": "completed", "outcome": "responded"}, sequence=2),
        ),
    )
    assert turn.user_text == "Hello"
    assert turn.assistant_text == "你好"
    assert turn.run_id == "run_123"
    assert turn.terminal_state == "response"


def test_from_run_summarizes_applied_changeset_without_diff_or_tool_output() -> None:
    turn = ConversationTurnProjector().from_run(
        "change color",
        (
            event("tool.completed", {"name": "read_file", "content": "secret body"}),
            event(
                "changeset.proposed",
                {
                    "changeset_id": "cs_demo",
                    "files": [
                        {
                            "path": "ThirdViewController.swift",
                            "operation": "create",
                            "unified_diff": "must-not-be-stored",
                        }
                    ],
                },
                sequence=2,
            ),
            event("changeset.applied", {"status": "applied"}, sequence=3),
            event("run.completed", {"state": "completed", "outcome": "changed"}, sequence=4),
        ),
    )
    blob = serialized(turn)
    assert turn.user_text == "change color"
    assert turn.run_id == "run_123"
    assert turn.terminal_state == "completed"
    assert "已应用" in turn.assistant_text
    assert "cs_demo" in turn.assistant_text
    assert "ThirdViewController.swift" in turn.assistant_text
    assert "secret body" not in blob
    assert "must-not-be-stored" not in blob
    assert '"events"' not in blob


def test_from_run_failed_and_cancelled_are_deterministic() -> None:
    projector = ConversationTurnProjector()
    cancelled = projector.from_run(
        "cancel me",
        (
            event("run.started", {"run_id": "run_456"}, run_id="run_456"),
            event("run.cancelled", {"reason": "cancelled_by_user"}, run_id="run_456", sequence=2),
        ),
    )
    failed = projector.from_run(
        "fail me",
        (
            event("run.started", {"run_id": "run_789"}, run_id="run_789"),
            event("run.failed", {"reason": "model_error"}, run_id="run_789", sequence=2),
        ),
    )
    assert cancelled.terminal_state == "cancelled"
    assert cancelled.assistant_text == "run run_456 已取消，工作区未应用该 Change Set。"
    assert failed.terminal_state == "failed"
    assert "run run_789 失败：model_error。" in failed.assistant_text
    assert "error=model_error" in failed.assistant_text


def test_from_run_recovery_only_references_run_id() -> None:
    turn = ConversationTurnProjector().from_run(
        "recover me",
        (
            event("run.started", {"run_id": "run_rec"}, run_id="run_rec"),
            event(
                "recovery.manual_required",
                {"classification": "manual_required", "checkpoint_id": "ckpt_secret"},
                run_id="run_rec",
                sequence=2,
            ),
        ),
    )
    blob = serialized(turn)
    assert turn.terminal_state == "recovery"
    assert turn.run_id == "run_rec"
    assert "run_rec" in turn.assistant_text
    assert "ckpt_secret" not in blob
    assert "checkpoint" not in blob


def test_from_run_empty_assistant_falls_back_to_summary() -> None:
    turn = ConversationTurnProjector().from_run(
        "Hello",
        (event("run.completed", {"state": "completed", "outcome": "responded"}),),
    )
    assert turn.assistant_text.strip()
    assert turn.terminal_state == "completed"
    assert turn.run_id == "run_123"
