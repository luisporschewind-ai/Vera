"""Recovery snapshot codec with explicit snapshot_version dispatch."""

from __future__ import annotations

import json

from vera.persistence.errors import StateVersionError
from vera.recovery.models import RecoverySnapshot


class SnapshotCodec:
    def encode(self, snapshot: RecoverySnapshot) -> bytes:
        payload = json.dumps(
            snapshot.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return payload.encode("utf-8")

    def decode(self, data: bytes | str) -> RecoverySnapshot:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateVersionError("invalid_snapshot") from exc
        if not isinstance(payload, dict) or "snapshot_version" not in payload:
            raise StateVersionError("missing_version")
        version = payload["snapshot_version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise StateVersionError("invalid_snapshot")
        if version != 1:
            raise StateVersionError("unsupported_version", version)
        try:
            return RecoverySnapshot.model_validate(payload)
        except Exception as exc:
            raise StateVersionError("invalid_snapshot", version) from exc
