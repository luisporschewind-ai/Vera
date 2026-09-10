"""Recursive redaction for secrets and sensitive field names."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class Redactor:
    _SENSITIVE_KEYS = {"api_key", "authorization", "token", "password", "secret"}

    def __init__(self, secret_values: Iterable[str]) -> None:
        self._secrets = tuple(
            sorted((value for value in secret_values if value), key=len, reverse=True)
        )

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in self._SENSITIVE_KEYS else self.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact(item) for item in value)
        if isinstance(value, str):
            redacted = value
            for secret in self._secrets:
                redacted = redacted.replace(secret, "[REDACTED]")
            return redacted
        return value
