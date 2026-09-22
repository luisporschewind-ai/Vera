"""Compatibility fixtures for optional Core-native Skills state."""

from __future__ import annotations

import json
from pathlib import Path

from vera.persistence.session_codec import SessionCodec
from vera.persistence.snapshot_codec import SnapshotCodec
from vera.recovery.models import RecoverySnapshot


def test_legacy_session_fixture_has_no_skill_state() -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "sessions"
    lines = (fixture / "v1-valid" / "session.jsonl").read_text(encoding="utf-8").splitlines()

    records = [
        SessionCodec().decode_line(
            line,
            expected_session_id="session_demo",
            expected_sequence=index,
        )
        for index, line in enumerate(lines, start=1)
    ]

    assert all("skill" not in record.model_dump(mode="json") for record in records)


def test_legacy_recovery_snapshot_defaults_to_no_skill() -> None:
    from tests.persistence.test_snapshot_codec import _snapshot

    payload = json.loads(SnapshotCodec().encode(_snapshot()))
    payload.pop("skill_snapshot", None)

    restored = SnapshotCodec().decode(json.dumps(payload))

    assert isinstance(restored, RecoverySnapshot)
    assert restored.skill_snapshot is None
