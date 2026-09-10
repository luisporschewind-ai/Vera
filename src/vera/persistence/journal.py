"""Append-only, ordered, private Event Journal."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from vera.contracts.events import EventEnvelope
from vera.redaction import Redactor


class JournalCorrupt(ValueError):
    """Raised when a journal is malformed or its sequence is not continuous."""


class EventJournal:
    def __init__(self, state_dir: Path, run_id: str, redactor: Redactor) -> None:
        self.state_dir = state_dir
        self.run_id = run_id
        self.redactor = redactor
        self.run_dir = state_dir / "runs" / run_id
        self.path = self.run_dir / "events.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.run_dir, 0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        os.chmod(self.path, 0o600)
        self._events = self._load()

    def _load(self) -> list[EventEnvelope]:
        return self.load_events(self.path, self.run_id)

    @staticmethod
    def load_events(path: Path, run_id: str) -> list[EventEnvelope]:
        """Load and validate an existing journal without touching the filesystem."""
        events: list[EventEnvelope] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = EventEnvelope.model_validate_json(line)
                except Exception as exc:
                    raise JournalCorrupt(f"invalid event at line {line_number}") from exc
                expected = len(events) + 1
                if event.run_id != run_id or event.sequence != expected:
                    raise JournalCorrupt(f"non-continuous event at line {line_number}")
                events.append(event)
        return events

    def append(self, event_type: str, payload: dict[str, object]) -> EventEnvelope:
        event = EventEnvelope(
            event_id=str(uuid4()),
            run_id=self.run_id,
            sequence=len(self._events) + 1,
            timestamp=datetime.now(UTC),
            type=event_type,
            payload=self.redactor.redact(payload),
        )
        serialized = event.model_dump_json() + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        self._events.append(event)
        return event

    def read_all(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._events)
