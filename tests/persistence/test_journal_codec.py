"""JournalCodec format and continuity tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vera.contracts.codec import ContractCodec
from vera.contracts.events import EventEnvelope
from vera.persistence.errors import StateVersionError
from vera.persistence.journal import JournalCorrupt
from vera.persistence.journal_codec import JournalCodec


def test_journal_codec_decodes_version_one_line() -> None:
    event = EventEnvelope(
        event_id="evt_1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        type="run.started",
        payload={},
    )
    line = ContractCodec().encode_event(event)
    decoded = JournalCodec().decode_line(line, "run_1", 1)
    assert decoded == event


def test_journal_codec_rejects_future_format() -> None:
    with pytest.raises(StateVersionError) as caught:
        JournalCodec().decode_line(b"{}", "run_1", 1, journal_format_version=99)
    assert caught.value.code == "unsupported_version"


def test_journal_codec_rejects_sequence_gap() -> None:
    event = EventEnvelope(
        event_id="evt_1",
        run_id="run_1",
        sequence=2,
        timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        type="run.started",
        payload={},
    )
    with pytest.raises(JournalCorrupt):
        JournalCodec().decode_line(ContractCodec().encode_event(event), "run_1", 1)
