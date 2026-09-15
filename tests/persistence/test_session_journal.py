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
from vera.persistence.session_journal import SessionJournal

STAMP = datetime(2026, 9, 16, 5, 0, tzinfo=UTC)


def _created(session_id: str = "session_demo", sequence: int = 1) -> ConversationSessionRecord:
    return ConversationSessionRecord(
        session_format_version=1,
        record_id=f"rec_{sequence}",
        session_id=session_id,
        sequence=sequence,
        timestamp=STAMP,
        type="session.created",
        payload=SessionCreatedPayload(
            type="session.created",
            workspace_identity="ws_demo",
            workspace_root="/workspace/demo",
            created_at=STAMP,
        ),
    )


def _turn(sequence: int = 2) -> ConversationSessionRecord:
    return ConversationSessionRecord(
        session_format_version=1,
        record_id=f"rec_{sequence}",
        session_id="session_demo",
        sequence=sequence,
        timestamp=STAMP,
        type="turn.committed",
        payload=TurnCommittedPayload(
            type="turn.committed",
            turn=ConversationTurn(
                user_text="你好",
                assistant_text="你好。",
                run_id="run_1",
                terminal_state="completed",
            ),
        ),
    )


def test_empty_and_continuous_journal(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    journal = SessionJournal(path, "session_demo")
    assert journal.read_all() == ()
    first = journal.append(_created())
    second = journal.append(_turn())
    assert [record.sequence for record in journal.read_all()] == [1, 2]
    assert first.type == "session.created"
    assert second.type == "turn.committed"
    assert path.read_bytes().endswith(b"\n")


def test_truncated_tail_is_repairable(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    journal = SessionJournal(path, "session_demo")
    journal.append(_created())
    path.write_bytes(path.read_bytes() + b'{"session_format_version":1')
    inspection = journal.inspect()
    assert inspection.repairable_tail_only is True
    assert inspection.failure_code == "truncated_tail"
    assert inspection.valid_through_sequence == 1
    with pytest.raises(JournalCorrupt) as caught:
        journal.read_all()
    assert caught.value.code == "truncated_tail"


def test_complete_illegal_line_and_mid_file_are_not_auto_repaired(tmp_path: Path) -> None:
    codec = SessionCodec()
    path = tmp_path / "session.jsonl"
    valid = codec.encode_record(_created()).decode("utf-8") + "\n"
    path.write_text(valid + "not-json\n", encoding="utf-8")
    journal = SessionJournal(path, "session_demo")
    inspection = journal.inspect()
    assert inspection.repairable_tail_only is False
    assert inspection.failure_code == "invalid_session_record"

    path.write_text("not-json\n" + valid, encoding="utf-8")
    inspection = SessionJournal(path, "session_demo").inspect()
    assert inspection.repairable_tail_only is False
    assert inspection.valid_through_sequence == 0


def test_sequence_hole_wrong_id_and_future_version(tmp_path: Path) -> None:
    codec = SessionCodec()
    path = tmp_path / "session.jsonl"
    created = codec.encode_record(_created()).decode("utf-8")
    skipped = codec.encode_record(_turn(sequence=3)).decode("utf-8")
    path.write_text(created + "\n" + skipped + "\n", encoding="utf-8")
    inspection = SessionJournal(path, "session_demo").inspect()
    assert inspection.failure_code == "session_sequence_mismatch"
    assert inspection.repairable_tail_only is False

    other = _created(session_id="session_other")
    path.write_text(codec.encode_record(other).decode("utf-8") + "\n", encoding="utf-8")
    inspection = SessionJournal(path, "session_demo").inspect()
    assert inspection.failure_code == "session_id_mismatch"

    future = created.replace('"session_format_version":1', '"session_format_version":2')
    path.write_text(future + "\n", encoding="utf-8")
    journal = SessionJournal(path, "session_demo")
    inspection = journal.inspect()
    assert inspection.failure_code == "unsupported_session_version"
    with pytest.raises(StateVersionError):
        journal.read_all()
