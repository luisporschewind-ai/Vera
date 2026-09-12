from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.codec import ContractCodec
from vera.contracts.events import EventEnvelope
from vera.persistence.journal import EventJournal, JournalCorrupt
from vera.redaction import Redactor


def _event_line(
    run_id: str = "run_1",
    sequence: int = 1,
    event_type: str = "run.started",
    payload: dict[str, object] | None = None,
) -> str:
    event = EventEnvelope(
        event_id=f"evt_{sequence}",
        run_id=run_id,
        sequence=sequence,
        timestamp=datetime(2026, 9, 12, tzinfo=UTC),
        type=event_type,
        payload=payload or {},
    )
    return ContractCodec().encode_event(event).decode("utf-8") + "\n"


def test_journal_assigns_monotonic_sequence_and_persists_jsonl(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    first = journal.append("run.started", {"goal": "test"})
    second = journal.append("tool.started", {"name": "read_file"})
    assert (first.sequence, second.sequence) == (1, 2)
    assert [event.type for event in journal.read_all()] == ["run.started", "tool.started"]
    assert (tmp_path / "runs" / "run_1").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "runs" / "run_1" / "events.jsonl").stat().st_mode & 0o777 == 0o600


def test_reopened_journal_continues_sequence(tmp_path: Path) -> None:
    EventJournal(tmp_path, run_id="run_1", redactor=Redactor([])).append("run.started", {})
    journal = EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert journal.append("run.completed", {}).sequence == 2


def test_journal_redacts_secrets_before_persist(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path, run_id="run_1", redactor=Redactor())
    journal.append(
        "run.failed",
        {
            "reason": "Authorization: Bearer sk-live-journal-secret-abcdef",
            "env": "GLM_API_KEY=sk-live-journal-secret-abcdef",
        },
    )
    body = (tmp_path / "runs" / "run_1" / "events.jsonl").read_text(encoding="utf-8")
    assert "sk-live-journal-secret-abcdef" not in body
    assert "[REDACTED]" in body


def test_journal_rejects_corrupt_or_noncontinuous_lines(tmp_path: Path) -> None:
    event_path = tmp_path / "runs" / "run_1" / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(JournalCorrupt) as caught:
        EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert caught.value.code == "mid_file_corrupt"
    assert "不要自动删除" in caught.value.advice


def test_journal_ignores_uncommitted_truncated_tail(tmp_path: Path) -> None:
    event_path = tmp_path / "runs" / "run_1" / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(
        _event_line() + '{"schema_version":1,"event_id":"partial"',
        encoding="utf-8",
    )
    journal = EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert len(journal.read_all()) == 1
    assert journal.append("run.completed", {}).sequence == 2


def test_journal_fails_closed_on_mid_file_corruption(tmp_path: Path) -> None:
    event_path = tmp_path / "runs" / "run_1" / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(_event_line() + "not-json\n" + _event_line(sequence=3), encoding="utf-8")
    original = event_path.read_bytes()
    with pytest.raises(JournalCorrupt) as caught:
        EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert caught.value.code == "mid_file_corrupt"
    assert event_path.read_bytes() == original


def test_journal_checksum_rejects_sequence_gap(tmp_path: Path) -> None:
    event_path = tmp_path / "runs" / "run_1" / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(_event_line() + _event_line(sequence=3), encoding="utf-8")
    with pytest.raises(JournalCorrupt) as caught:
        EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert caught.value.code == "checksum_mismatch"


def test_journal_rejects_missing_and_dangerous_fields(tmp_path: Path) -> None:
    event_path = tmp_path / "runs" / "run_1" / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    missing = (
        '{"schema_version":1,"run_id":"run_1","sequence":1,'
        '"timestamp":"2026-09-12T00:00:00Z","type":"run.started","payload":{}}\n'
    )
    event_path.write_text(missing, encoding="utf-8")
    with pytest.raises(JournalCorrupt) as caught:
        EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert caught.value.code == "missing_field"

    dangerous = _event_line().rstrip("\n")
    payload = dangerous[:-1] + ',"__proto__":{"x":1}}\n'
    event_path.write_text(payload, encoding="utf-8")
    with pytest.raises(JournalCorrupt) as caught_extra:
        EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
    assert caught_extra.value.code == "unexpected_field"
