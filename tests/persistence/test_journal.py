from pathlib import Path

import pytest

from vera.persistence.journal import EventJournal, JournalCorrupt
from vera.redaction import Redactor


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
    with pytest.raises(JournalCorrupt):
        EventJournal(tmp_path, run_id="run_1", redactor=Redactor([]))
