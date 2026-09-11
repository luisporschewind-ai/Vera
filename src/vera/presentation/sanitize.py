"""Sanitize untrusted terminal text before rendering."""

from __future__ import annotations

import re

_ANSI_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANSI_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_OTHER_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_terminal_text(value: str) -> str:
    """Remove ANSI/OSC and other C0 controls except tab/newline/carriage-return."""

    cleaned = _ANSI_OSC.sub("", value)
    cleaned = _ANSI_CSI.sub("", cleaned)
    return _OTHER_CONTROLS.sub("", cleaned)
