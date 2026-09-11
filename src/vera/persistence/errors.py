"""State format version errors for private persistence codecs."""

from __future__ import annotations


class StateVersionError(ValueError):
    """Raised when private state uses an unsupported or missing format version."""

    def __init__(self, code: str, version: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.version = version


class JournalCorrupt(ValueError):
    """Raised when a journal is malformed or its sequence is not continuous."""
