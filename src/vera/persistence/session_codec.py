"""Deterministic encoder/decoder for conversation session journal records."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import ValidationError

from vera.contracts.sessions import ConversationSessionRecord
from vera.persistence.decode import parse_json_object
from vera.persistence.errors import JournalCorrupt, PersistenceFault, StateVersionError

CURRENT_SESSION_FORMAT_VERSION = 1


def _to_json(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    return value


class SessionCodec:
    def encode_record(self, record: ConversationSessionRecord) -> bytes:
        payload = _to_json(record.model_dump(mode="python"))
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def decode_line(
        self,
        line: str,
        *,
        expected_session_id: str,
        expected_sequence: int,
    ) -> ConversationSessionRecord:
        try:
            payload = parse_json_object(line)
        except PersistenceFault as exc:
            raise JournalCorrupt(str(exc), code="invalid_session_record") from exc
        version = payload.get("session_format_version")
        if version != CURRENT_SESSION_FORMAT_VERSION:
            if isinstance(version, int) and not isinstance(version, bool):
                raise StateVersionError("unsupported_session_version", version)
            raise JournalCorrupt("invalid session record", code="invalid_session_record")
        try:
            record = ConversationSessionRecord.model_validate(payload)
        except ValidationError as exc:
            raise JournalCorrupt(str(exc), code="invalid_session_record") from exc
        if record.session_id != expected_session_id:
            raise JournalCorrupt("session id mismatch", code="session_id_mismatch")
        if record.sequence != expected_sequence:
            raise JournalCorrupt("session sequence mismatch", code="session_sequence_mismatch")
        return record
