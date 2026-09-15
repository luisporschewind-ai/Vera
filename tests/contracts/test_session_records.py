from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vera.contracts.sessions import (
    ContextCompactedPayload,
    ConversationSessionRecord,
    ConversationTurn,
    SessionClosedPayload,
    SessionCreatedPayload,
    SessionRenamedPayload,
    TurnCommittedPayload,
)

STAMP = datetime(2026, 9, 16, 4, 0, tzinfo=UTC)


def _record(
    payload: object,
    *,
    record_type: str | None = None,
    sequence: int = 1,
) -> ConversationSessionRecord:
    return ConversationSessionRecord(
        session_format_version=1,
        record_id="rec_1",
        session_id="session_1",
        sequence=sequence,
        timestamp=STAMP,
        type=record_type or payload.type,  # type: ignore[union-attr]
        payload=payload,  # type: ignore[arg-type]
    )


def test_five_valid_records_round_trip() -> None:
    created = _record(
        SessionCreatedPayload(
            type="session.created",
            workspace_identity="ws_abc",
            workspace_root="/workspace/demo",
            created_at=STAMP,
        )
    )
    turned = _record(
        TurnCommittedPayload(
            type="turn.committed",
            turn=ConversationTurn(
                user_text="列出文件",
                assistant_text="目录里有 README.md。",
                run_id="run_1",
                terminal_state="completed",
            ),
        ),
        sequence=2,
    )
    compacted = _record(
        ContextCompactedPayload(
            type="context.compacted",
            summary="用户询问了目录内容。",
            through_sequence=2,
            compact_count=1,
        ),
        sequence=3,
    )
    renamed = _record(
        SessionRenamedPayload(type="session.renamed", title="列出文件"),
        sequence=4,
    )
    closed = _record(SessionClosedPayload(type="session.closed"), sequence=5)

    for record in (created, turned, compacted, renamed, closed):
        restored = ConversationSessionRecord.model_validate_json(record.model_dump_json())
        assert restored == record


def test_created_payload_allows_repair_fields() -> None:
    record = _record(
        SessionCreatedPayload(
            type="session.created",
            workspace_identity="ws_abc",
            workspace_root="/workspace/demo",
            created_at=STAMP,
            repaired_from_session_id="session_old",
            repaired_through_sequence=3,
            source_digest="digest_1",
        )
    )
    assert record.payload.repaired_from_session_id == "session_old"


def test_blank_texts_and_negative_sequence_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ConversationTurn(
            user_text=" ",
            assistant_text="ok",
            run_id=None,
            terminal_state="response",
        )
    with pytest.raises(ValidationError):
        ConversationTurn(
            user_text="ok",
            assistant_text="",
            run_id=None,
            terminal_state="response",
        )
    with pytest.raises(ValidationError):
        _record(
            SessionCreatedPayload(
                type="session.created",
                workspace_identity="ws_abc",
                workspace_root="/workspace/demo",
                created_at=STAMP,
            ),
            sequence=0,
        )
    with pytest.raises(ValidationError):
        _record(
            SessionCreatedPayload(
                type="session.created",
                workspace_identity="ws_abc",
                workspace_root="/workspace/demo",
                created_at=STAMP,
            ),
            sequence=-1,
        )


def test_payload_type_mismatch_and_extra_fields_are_rejected() -> None:
    payload = SessionClosedPayload(type="session.closed")
    with pytest.raises(ValidationError):
        ConversationSessionRecord(
            session_format_version=1,
            record_id="rec_1",
            session_id="session_1",
            sequence=1,
            timestamp=STAMP,
            type="session.created",
            payload=payload,
        )
    with pytest.raises(ValidationError):
        SessionRenamedPayload(type="session.renamed", title="x", extra="no")
    with pytest.raises(ValidationError):
        ConversationTurn(
            user_text="a",
            assistant_text="b",
            run_id=None,
            terminal_state="done",
        )


def test_records_are_frozen() -> None:
    record = _record(SessionClosedPayload(type="session.closed"))
    with pytest.raises(ValidationError):
        record.sequence = 2  # type: ignore[misc]
    with pytest.raises(ValidationError):
        record.payload.type = "session.renamed"  # type: ignore[misc]
