"""Append-only, ordered, private Event Journal."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from vera.contracts.codec import ContractCodec
from vera.contracts.errors import classify_os_error
from vera.contracts.events import EventEnvelope
from vera.persistence.errors import JournalCorrupt, PersistenceFault, StateVersionError
from vera.persistence.journal_codec import JournalCodec
from vera.persistence.run_manifest import RunManifest, RunManifestStore
from vera.redaction import Redactor

__all__ = ["EventJournal", "JournalCorrupt"]


class EventJournal:
    def __init__(
        self,
        state_dir: Path,
        run_id: str,
        redactor: Redactor,
        *,
        ensure_manifest: bool = True,
    ) -> None:
        self.state_dir = state_dir
        self.run_id = run_id
        self.redactor = redactor
        self.run_dir = state_dir / "runs" / run_id
        self.path = self.run_dir / "events.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.run_dir, 0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        os.chmod(self.path, 0o600)
        self._manifest_store = RunManifestStore(state_dir)
        self._journal_format_version = self._resolve_format_version(ensure_manifest=ensure_manifest)
        self._events = self._load()

    def _resolve_format_version(self, *, ensure_manifest: bool) -> int:
        if self._manifest_store.exists(self.run_id):
            return self._manifest_store.load(self.run_id).journal_format_version
        if ensure_manifest and not self.path.stat().st_size:
            self._manifest_store.save(RunManifest(run_id=self.run_id))
            return 1
        # Legacy directories without manifest are readable as journal format v1.
        return 1

    def _load(self) -> list[EventEnvelope]:
        return self.load_events(
            self.path,
            self.run_id,
            journal_format_version=self._journal_format_version,
        )

    @staticmethod
    def load_events(
        path: Path,
        run_id: str,
        *,
        journal_format_version: int = 1,
        codec: JournalCodec | None = None,
    ) -> list[EventEnvelope]:
        """Load and validate an existing journal without touching the filesystem."""
        reader = codec or JournalCodec(ContractCodec())
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise PersistenceFault(classify_os_error(exc), str(exc)) from exc
        if not raw:
            return []
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JournalCorrupt(
                "invalid encoding",
                code="invalid_encoding",
            ) from exc
        complete_lines = text.split("\n")[:-1]
        events: list[EventEnvelope] = []
        for line_number, line in enumerate(complete_lines, start=1):
            if not line.strip():
                continue
            try:
                event = reader.decode_line(
                    line,
                    run_id,
                    len(events) + 1,
                    journal_format_version=journal_format_version,
                )
            except StateVersionError:
                raise
            except JournalCorrupt as exc:
                raise JournalCorrupt(
                    f"invalid event at line {line_number}",
                    code=exc.code,
                    advice=exc.advice,
                    line=line_number,
                ) from exc
            except Exception as exc:
                raise JournalCorrupt(
                    f"invalid event at line {line_number}",
                    code="mid_file_corrupt",
                    line=line_number,
                ) from exc
            events.append(event)
        return events

    def append(self, event_type: str, payload: dict[str, object]) -> EventEnvelope:
        if self._journal_format_version != 1:
            raise StateVersionError("unsupported_version", self._journal_format_version)
        if not self._manifest_store.exists(self.run_id):
            self._manifest_store.save(RunManifest(run_id=self.run_id))
            self._journal_format_version = 1
        event = EventEnvelope(
            event_id=str(uuid4()),
            run_id=self.run_id,
            sequence=len(self._events) + 1,
            timestamp=datetime.now(UTC),
            type=event_type,
            payload=self.redactor.redact(payload),
        )
        serialized = ContractCodec().encode_event(event).decode("utf-8") + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise PersistenceFault(classify_os_error(exc), str(exc)) from exc
        self._events.append(event)
        return event

    def read_all(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._events)
