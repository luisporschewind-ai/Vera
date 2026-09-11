"""SnapshotCodec version dispatch tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryStage
from vera.persistence.errors import StateVersionError
from vera.persistence.snapshot_codec import SnapshotCodec
from vera.recovery.models import RecoverySnapshot


def _snapshot() -> RecoverySnapshot:
    root = Path("/tmp/ws")
    now = datetime(2026, 9, 11, tzinfo=UTC)
    return RecoverySnapshot(
        run_id="run_1",
        workspace_root=root,
        workspace_identity="a" * 64,
        command=StartRun(goal="demo", workspace_root=root, model_profile="default"),
        stage=RecoveryStage.STARTED,
        last_event_sequence=1,
        created_at=now,
        updated_at=now,
        vera_version="0.1.0",
    )


def test_snapshot_codec_round_trips() -> None:
    codec = SnapshotCodec()
    snapshot = _snapshot()
    assert codec.decode(codec.encode(snapshot)) == snapshot


def test_snapshot_codec_rejects_future_version() -> None:
    data = b'{"snapshot_version":99,"run_id":"run_1"}'
    with pytest.raises(StateVersionError, match="unsupported_version"):
        SnapshotCodec().decode(data)


def test_snapshot_codec_rejects_missing_version() -> None:
    with pytest.raises(StateVersionError) as caught:
        SnapshotCodec().decode(b'{"run_id":"run_1"}')
    assert caught.value.code == "missing_version"
