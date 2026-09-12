"""Journal line codec with format-version awareness."""

from __future__ import annotations

from vera.contracts.codec import ContractCodec, ContractVersionError
from vera.contracts.errors import CoreErrorCode
from vera.contracts.events import EventEnvelope
from vera.persistence.decode import inspect_payload, parse_json_object
from vera.persistence.errors import JournalCorrupt, PersistenceFault, StateVersionError

CURRENT_JOURNAL_FORMAT_VERSION = 1

_EVENT_ALLOWED = frozenset(EventEnvelope.model_fields)
_EVENT_REQUIRED = frozenset(
    {"schema_version", "event_id", "run_id", "sequence", "timestamp", "type", "payload"}
)


class JournalCodec:
    def __init__(self, contract_codec: ContractCodec | None = None) -> None:
        self.contract_codec = contract_codec or ContractCodec()

    def decode_line(
        self,
        data: bytes | str,
        run_id: str,
        expected_sequence: int,
        *,
        journal_format_version: int = CURRENT_JOURNAL_FORMAT_VERSION,
    ) -> EventEnvelope:
        if journal_format_version != CURRENT_JOURNAL_FORMAT_VERSION:
            raise StateVersionError("unsupported_version", journal_format_version)
        try:
            payload = parse_json_object(data)
            inspect_payload(
                payload,
                allowed_keys=_EVENT_ALLOWED,
                required_keys=_EVENT_REQUIRED,
                version_key="schema_version",
                supported_versions=frozenset({1}),
            )
        except PersistenceFault as exc:
            if exc.code == CoreErrorCode.UNSUPPORTED_VERSION.value:
                raise StateVersionError(exc.code, exc.version) from exc
            if exc.code == "missing_version":
                raise JournalCorrupt(
                    "missing version",
                    code=CoreErrorCode.MISSING_FIELD.value,
                ) from exc
            raise JournalCorrupt(str(exc), code=exc.code) from exc
        try:
            event = self.contract_codec.decode_event(
                data.encode("utf-8") if isinstance(data, str) else data
            )
        except ContractVersionError as exc:
            if exc.code == "unsupported_version":
                raise StateVersionError(exc.code, exc.version) from exc
            raise JournalCorrupt(
                "invalid event",
                code=CoreErrorCode.MID_FILE_CORRUPT.value,
            ) from exc
        if event.run_id != run_id or event.sequence != expected_sequence:
            raise JournalCorrupt(
                "non-continuous event",
                code=CoreErrorCode.CHECKSUM_MISMATCH.value,
            )
        return event
