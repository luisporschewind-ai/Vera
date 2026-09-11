"""Journal line codec with format-version awareness."""

from __future__ import annotations

from vera.contracts.codec import ContractCodec, ContractVersionError
from vera.contracts.events import EventEnvelope
from vera.persistence.errors import JournalCorrupt, StateVersionError


class JournalCodec:
    def __init__(self, contract_codec: ContractCodec | None = None) -> None:
        self.contract_codec = contract_codec or ContractCodec()

    def decode_line(
        self,
        data: bytes | str,
        run_id: str,
        expected_sequence: int,
        *,
        journal_format_version: int = 1,
    ) -> EventEnvelope:
        if journal_format_version != 1:
            raise StateVersionError("unsupported_version", journal_format_version)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        try:
            event = self.contract_codec.decode_event(raw)
        except ContractVersionError as exc:
            if exc.code == "unsupported_version":
                raise StateVersionError(exc.code, exc.version) from exc
            raise JournalCorrupt("invalid event") from exc
        if event.run_id != run_id or event.sequence != expected_sequence:
            raise JournalCorrupt("non-continuous event")
        return event
