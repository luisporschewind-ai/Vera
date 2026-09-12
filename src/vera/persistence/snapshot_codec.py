"""Recovery snapshot codec with explicit snapshot_version dispatch."""

from __future__ import annotations

import json

from pydantic import ValidationError

from vera.contracts.errors import CoreErrorCode
from vera.persistence.decode import classify_validation_error, inspect_payload, parse_json_object
from vera.persistence.errors import PersistenceFault, StateVersionError
from vera.recovery.models import RecoverySnapshot

_SNAPSHOT_ALLOWED = frozenset(RecoverySnapshot.model_fields)
_SNAPSHOT_REQUIRED = frozenset(
    {
        "snapshot_version",
        "run_id",
        "workspace_root",
        "workspace_identity",
        "command",
        "stage",
        "last_event_sequence",
        "created_at",
        "updated_at",
        "vera_version",
    }
)


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
        try:
            payload = parse_json_object(data)
            version = inspect_payload(
                payload,
                allowed_keys=_SNAPSHOT_ALLOWED,
                required_keys=_SNAPSHOT_REQUIRED,
                version_key="snapshot_version",
                supported_versions=frozenset({1}),
            )
        except PersistenceFault as exc:
            if exc.code == CoreErrorCode.UNSUPPORTED_VERSION.value:
                raise StateVersionError(exc.code, exc.version) from exc
            raise StateVersionError(exc.code, exc.version) from exc
        try:
            return RecoverySnapshot.model_validate(payload)
        except ValidationError as exc:
            code = classify_validation_error(exc)
            if code == "invalid_record":
                code = "invalid_snapshot"
            raise StateVersionError(code, version) from exc
        except Exception as exc:
            message = str(exc).lower()
            code = (
                CoreErrorCode.CHECKSUM_MISMATCH.value if "hash" in message else "invalid_snapshot"
            )
            raise StateVersionError(code, version) from exc
