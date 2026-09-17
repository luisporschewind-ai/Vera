"""Strict conversation session journal reader and appender."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from vera.contracts.sessions import ConversationSessionRecord
from vera.persistence.errors import JournalCorrupt, StateVersionError
from vera.persistence.private_writer import PrivateAppendWriter
from vera.persistence.session_codec import SessionCodec
from vera.redaction import Redactor


@dataclass(frozen=True)
class SessionJournalInspection:
    records: tuple[ConversationSessionRecord, ...]
    source_digest: str
    failure_code: str | None
    repairable_tail_only: bool
    valid_through_sequence: int
    raw_bytes: bytes


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SessionJournal:
    def __init__(
        self,
        path: Path,
        session_id: str,
        *,
        codec: SessionCodec | None = None,
        redactor: Redactor | None = None,
        writer: PrivateAppendWriter | None = None,
    ) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.codec = codec or SessionCodec()
        self.redactor = redactor or Redactor([])
        self.writer = writer or PrivateAppendWriter()

    def inspect(self) -> SessionJournalInspection:
        if not self.path.exists():
            empty = b""
            return SessionJournalInspection((), _digest(empty), None, False, 0, empty)
        if self.path.is_symlink():
            raise JournalCorrupt("session journal is a symlink", code="invalid_session_record")
        raw = self.path.read_bytes()
        if not raw:
            return SessionJournalInspection((), _digest(raw), None, False, 0, raw)
        text = raw.decode("utf-8")
        ends_with_newline = text.endswith("\n")
        pieces = text.split("\n")
        if ends_with_newline:
            lines = [piece for piece in pieces if piece != ""]
            remainder = ""
        else:
            lines = pieces[:-1]
            remainder = pieces[-1]
        records: list[ConversationSessionRecord] = []
        for index, line in enumerate(lines, start=1):
            try:
                record = self.codec.decode_line(
                    line,
                    expected_session_id=self.session_id,
                    expected_sequence=index,
                )
            except StateVersionError as exc:
                return SessionJournalInspection(
                    tuple(records),
                    _digest(raw),
                    exc.code,
                    False,
                    records[-1].sequence if records else 0,
                    raw,
                )
            except JournalCorrupt as exc:
                return SessionJournalInspection(
                    tuple(records),
                    _digest(raw),
                    exc.code if records or index > 1 else exc.code,
                    False,
                    records[-1].sequence if records else 0,
                    raw,
                )
            records.append(record)
        if remainder:
            return SessionJournalInspection(
                tuple(records),
                _digest(raw),
                "truncated_tail",
                True,
                records[-1].sequence if records else 0,
                raw,
            )
        return SessionJournalInspection(
            tuple(records),
            _digest(raw),
            None,
            False,
            records[-1].sequence if records else 0,
            raw,
        )

    def read_all(self) -> tuple[ConversationSessionRecord, ...]:
        inspection = self.inspect()
        if inspection.failure_code is None:
            return inspection.records
        if inspection.failure_code == "unsupported_session_version":
            raise StateVersionError(inspection.failure_code)
        if inspection.repairable_tail_only:
            raise JournalCorrupt(
                "truncated session journal tail",
                code="truncated_tail",
            )
        raise JournalCorrupt(
            "session journal requires manual repair",
            code=inspection.failure_code,
        )

    def append(self, record: ConversationSessionRecord) -> ConversationSessionRecord:
        inspection = self.inspect()
        if inspection.failure_code is not None:
            if inspection.failure_code == "unsupported_session_version":
                raise StateVersionError(inspection.failure_code)
            raise JournalCorrupt(
                "cannot append to a damaged session journal",
                code=inspection.failure_code,
            )
        expected = inspection.valid_through_sequence + 1
        if record.session_id != self.session_id or record.sequence != expected:
            raise JournalCorrupt("session sequence mismatch", code="session_sequence_mismatch")
        redacted = ConversationSessionRecord.model_validate(
            self.redactor.redact(record.model_dump(mode="python"))
        )
        encoded = self.codec.encode_record(redacted)
        self.writer.append_line(self.path, encoded)
        return redacted
