from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.sessions import (
    ConversationSessionRecord,
    ConversationTurn,
    SessionCreatedPayload,
    TurnCommittedPayload,
)
from vera.persistence.errors import JournalCorrupt, StateVersionError
from vera.persistence.session_codec import SessionCodec

STAMP = datetime(2026, 9, 16, 4, 0, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "sessions"


def _created() -> ConversationSessionRecord:
    return ConversationSessionRecord(
        session_format_version=1,
        record_id="rec_1",
        session_id="session_demo",
        sequence=1,
        timestamp=STAMP,
        type="session.created",
        payload=SessionCreatedPayload(
            type="session.created",
            workspace_identity="ws_demo",
            workspace_root="/workspace/demo",
            created_at=STAMP,
        ),
    )


def test_encode_is_deterministic_utf8_json_without_newline() -> None:
    codec = SessionCodec()
    encoded = codec.encode_record(_created())
    assert encoded == codec.encode_record(_created())
    text = encoded.decode("utf-8")
    assert not text.endswith("\n")
    assert text.index('"record_id"') < text.index('"session_id"')
    assert "2026-09-16T04:00:00Z" in text
    assert "\\u" not in text


def test_cjk_and_redacted_text_round_trip() -> None:
    codec = SessionCodec()
    record = ConversationSessionRecord(
        session_format_version=1,
        record_id="rec_2",
        session_id="session_demo",
        sequence=2,
        timestamp=STAMP,
        type="turn.committed",
        payload=TurnCommittedPayload(
            type="turn.committed",
            turn=ConversationTurn(
                user_text="密钥是 [REDACTED]",
                assistant_text="已忽略凭据，继续看 README。",
                run_id=None,
                terminal_state="response",
            ),
        ),
    )
    restored = codec.decode_line(
        codec.encode_record(record).decode("utf-8"),
        expected_session_id="session_demo",
        expected_sequence=2,
    )
    assert restored == record
    assert "[REDACTED]" in restored.payload.turn.user_text  # type: ignore[union-attr]


def test_decode_rejects_version_id_and_sequence_errors() -> None:
    codec = SessionCodec()
    line = codec.encode_record(_created()).decode("utf-8")
    future = line.replace('"session_format_version":1', '"session_format_version":2')
    with pytest.raises(StateVersionError) as version_error:
        codec.decode_line(future, expected_session_id="session_demo", expected_sequence=1)
    assert version_error.value.code == "unsupported_session_version"

    with pytest.raises(JournalCorrupt) as id_error:
        codec.decode_line(line, expected_session_id="session_other", expected_sequence=1)
    assert id_error.value.code == "session_id_mismatch"

    with pytest.raises(JournalCorrupt) as seq_error:
        codec.decode_line(line, expected_session_id="session_demo", expected_sequence=2)
    assert seq_error.value.code == "session_sequence_mismatch"

    with pytest.raises(JournalCorrupt) as invalid:
        codec.decode_line("{", expected_session_id="session_demo", expected_sequence=1)
    assert invalid.value.code == "invalid_session_record"


def test_v1_fixture_replays_and_v2_is_rejected() -> None:
    codec = SessionCodec()
    lines = (FIXTURES / "v1-valid" / "session.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    decoded = [
        codec.decode_line(line, expected_session_id="session_demo", expected_sequence=index)
        for index, line in enumerate(lines, start=1)
    ]
    assert [record.type for record in decoded] == [
        "session.created",
        "session.renamed",
        "turn.committed",
        "context.compacted",
        "session.closed",
    ]
    assert decoded[2].payload.turn.user_text == "列出文件"  # type: ignore[union-attr]
    future = (FIXTURES / "v2-future" / "session.jsonl").read_text(encoding="utf-8").splitlines()[0]
    with pytest.raises(StateVersionError) as caught:
        codec.decode_line(future, expected_session_id="session_demo", expected_sequence=1)
    assert caught.value.code == "unsupported_session_version"
