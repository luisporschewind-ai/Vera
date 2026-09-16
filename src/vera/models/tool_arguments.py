"""Decode provider tool-call argument payloads."""

from __future__ import annotations

import json
from typing import Any

from vera.contracts import JsonValue

INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"


def decode_tool_arguments(raw: object) -> tuple[dict[str, JsonValue], str | None]:
    """Parse tool arguments without killing the model turn.

    Incomplete JSON, arrays, and non-objects become an empty dict plus
    ``invalid_tool_arguments`` so Runtime can write a tool error back.
    Missing names remain the adapter's responsibility.
    """

    if raw is None:
        return {}, None
    if isinstance(raw, dict):
        return _as_object(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {}, INVALID_TOOL_ARGUMENTS
    if not isinstance(raw, str):
        return {}, INVALID_TOOL_ARGUMENTS
    text = raw.strip()
    if not text:
        return {}, None
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError:
        return {}, INVALID_TOOL_ARGUMENTS
    return _as_object(parsed)


def _as_object(parsed: object) -> tuple[dict[str, JsonValue], str | None]:
    if isinstance(parsed, dict) and all(isinstance(key, str) for key in parsed):
        return parsed, None
    return {}, INVALID_TOOL_ARGUMENTS
