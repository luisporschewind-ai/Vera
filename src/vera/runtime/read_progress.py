"""Observe actual read results; never cache or bypass permissions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from vera.models.base import ModelToolCall

if TYPE_CHECKING:
    from vera.runtime.context import RunContext

READ_ONLY_TOOLS = frozenset(
    {"read", "read_file", "ls", "list_directory", "find", "grep", "search_text"}
)


def observe_read(context: RunContext, call: ModelToolCall, fingerprint: str, ok: bool) -> bool:
    if call.name not in READ_ONLY_TOOLS or not ok:
        context.read_observations.clear()
        context.unchanged_read_streak = 0
        context.read_warning_pending = False
        return False
    signature = json.dumps([call.name, call.arguments], sort_keys=True, ensure_ascii=False)
    if context.read_observations.get(signature) == fingerprint:
        context.unchanged_read_streak += 1
    else:
        context.unchanged_read_streak = 0
    context.read_observations[signature] = fingerprint
    if len(context.read_observations) > 128:
        del context.read_observations[next(iter(context.read_observations))]
    return context.unchanged_read_streak == 4
