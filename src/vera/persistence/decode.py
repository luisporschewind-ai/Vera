"""Shared private-state decode, validation, and error mapping."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from vera.contracts.errors import CoreErrorCode
from vera.persistence.errors import PersistenceFault

DANGEROUS_FIELDS = frozenset(
    {
        "__proto__",
        "constructor",
        "prototype",
        "__defineGetter__",
        "__defineSetter__",
        "__lookupGetter__",
        "__lookupSetter__",
    }
)


def parse_json_object(data: bytes | str) -> dict[str, Any]:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PersistenceFault(
            CoreErrorCode.INVALID_ENCODING.value,
            "invalid encoding",
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PersistenceFault(
            CoreErrorCode.MID_FILE_CORRUPT.value,
            "invalid json",
        ) from exc
    if not isinstance(payload, dict):
        raise PersistenceFault(
            CoreErrorCode.MID_FILE_CORRUPT.value,
            "json object required",
        )
    return payload


def inspect_payload(
    payload: Mapping[str, Any],
    *,
    allowed_keys: frozenset[str],
    required_keys: frozenset[str],
    version_key: str,
    supported_versions: frozenset[int],
) -> int:
    extra = set(payload) - set(allowed_keys)
    if extra:
        raise PersistenceFault(
            CoreErrorCode.UNEXPECTED_FIELD.value,
            f"unexpected field: {sorted(extra)[0]}",
        )
    if version_key not in payload:
        raise PersistenceFault("missing_version", "missing version")
    version = payload[version_key]
    if not isinstance(version, int) or isinstance(version, bool):
        raise PersistenceFault(
            CoreErrorCode.MISSING_FIELD.value,
            f"invalid {version_key}",
        )
    if version not in supported_versions:
        raise PersistenceFault(
            CoreErrorCode.UNSUPPORTED_VERSION.value,
            "unsupported_version",
            version=version,
        )
    missing = required_keys - set(payload)
    if missing:
        raise PersistenceFault(
            CoreErrorCode.MISSING_FIELD.value,
            f"missing field: {sorted(missing)[0]}",
        )
    return version


def classify_validation_error(exc: ValidationError) -> str:
    for error in exc.errors():
        error_type = str(error.get("type", ""))
        message = str(error.get("msg", "")).lower()
        if error_type == "extra_forbidden":
            return CoreErrorCode.UNEXPECTED_FIELD.value
        if error_type == "missing":
            return CoreErrorCode.MISSING_FIELD.value
        if "hash" in message or "checksum" in message:
            return CoreErrorCode.CHECKSUM_MISMATCH.value
    return "invalid_record"
