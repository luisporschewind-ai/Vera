"""SnapshotCodec version dispatch tests."""

from __future__ import annotations

import json
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
    assert "保留原文件" in caught.value.advice


def test_snapshot_codec_rejects_missing_and_dangerous_fields() -> None:
    snapshot = _snapshot()
    payload = json.loads(SnapshotCodec().encode(snapshot).decode("utf-8"))
    del payload["run_id"]
    with pytest.raises(StateVersionError) as missing:
        SnapshotCodec().decode(json.dumps(payload))
    assert missing.value.code == "missing_field"

    payload = json.loads(SnapshotCodec().encode(snapshot).decode("utf-8"))
    payload["__proto__"] = {"admin": True}
    with pytest.raises(StateVersionError) as extra:
        SnapshotCodec().decode(json.dumps(payload))
    assert extra.value.code == "unexpected_field"


def test_snapshot_codec_rejects_checksum_mismatch() -> None:
    snapshot = _snapshot()
    payload = json.loads(SnapshotCodec().encode(snapshot).decode("utf-8"))
    payload["workspace_identity"] = "b" * 64
    decoded = SnapshotCodec().decode(json.dumps(payload))
    assert decoded.workspace_identity == "b" * 64
    payload["built_changeset"] = {
        "change_set": {
            "schema_version": 1,
            "changeset_id": "cs_1",
            "run_id": "run_1",
            "summary": "edit",
            "files": [
                {
                    "schema_version": 1,
                    "operation": "update",
                    "path": "a.py",
                    "before_hash": "0" * 64,
                    "after_hash": "1" * 64,
                    "unified_diff": "@@\n",
                }
            ],
            "verification": [],
            "content_hash": "c" * 64,
        },
        "intended_content_b64": {"a.py": "YWZ0ZXI="},
        "path_facts": {},
    }
    with pytest.raises(StateVersionError) as caught:
        SnapshotCodec().decode(json.dumps(payload))
    assert caught.value.code == "checksum_mismatch"
