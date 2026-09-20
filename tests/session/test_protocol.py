import json
from datetime import UTC, datetime

import pytest

from vera.contracts.events import EventEnvelope
from vera.session.actions import (
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    SubmitPrompt,
)
from vera.session.protocol import (
    SessionActionCodec,
    SessionRecord,
    SessionRecordCodec,
    encode_action,
)


def test_decode_prompt_submit() -> None:
    action = SessionActionCodec.decode('{"schema_version":1,"type":"prompt.submit","text":"你好"}')
    assert action == SubmitPrompt(text="你好")


def test_decode_rejects_unknown_schema() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        SessionActionCodec.decode('{"schema_version":2,"type":"session.close"}')


def test_encode_action_round_trip() -> None:
    line = encode_action(ExecuteSlashCommand(raw="/status"))
    decoded = SessionActionCodec.decode(line)
    assert decoded == ExecuteSlashCommand(raw="/status")


def test_queue_and_editor_actions_round_trip() -> None:
    for action in (
        QueuePrompt(text="later"),
        ClearQueuedPrompt(),
        ConfirmExternalEditor(accept=False),
        OpenExternalEditor(text="draft"),
    ):
        assert SessionActionCodec.decode(encode_action(action)) == action


def test_session_record_event_only() -> None:
    event = EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="run.completed",
        payload={"state": "completed"},
    )
    record = SessionRecord(record_type="event", event=event)
    payload = json.loads(SessionRecordCodec.encode(record))
    assert payload["record_type"] == "event"
    assert payload.get("stream") is None
    assert CloseSession().type == "session.close"


def test_session_record_preserves_git_lifecycle_event_for_json_clients() -> None:
    event = EventEnvelope(
        event_id="e-git",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="git.operation.manual_required",
        payload={"operation": "git_commit", "error_code": "manual_required"},
    )
    payload = json.loads(SessionRecordCodec.encode(SessionRecord(record_type="event", event=event)))

    assert payload["event"]["type"] == "git.operation.manual_required"
    assert payload["event"]["payload"]["error_code"] == "manual_required"
