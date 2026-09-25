"""Detect provider tool-call markup that leaked into assistant text."""

from __future__ import annotations

from dataclasses import dataclass, field

LEAKED_TOOL_MARKERS: tuple[str, ...] = (
    "<｜DSML｜",
    "</｜DSML｜",
    "<|DSML|",
    "</|DSML|",
    "<｜tool▁calls▁begin｜>",
    "<｜tool▁call▁begin｜>",
)


def find_leaked_tool_markup(text: str | None) -> int | None:
    """Return the index of the first leaked marker, or None."""

    if not text:
        return None
    hits = [index for marker in LEAKED_TOOL_MARKERS if (index := text.find(marker)) >= 0]
    return min(hits) if hits else None


def strip_leaked_tool_markup(text: str | None) -> str:
    """Keep only the prose before the first leaked marker."""

    if not text:
        return ""
    index = find_leaked_tool_markup(text)
    return (text if index is None else text[:index]).strip()


def _pending_marker_prefix(text: str) -> int:
    """Length of the longest suffix of text that could still grow into a marker."""

    longest = 0
    for marker in LEAKED_TOOL_MARKERS:
        for size in range(min(len(marker) - 1, len(text)), longest, -1):
            if text.endswith(marker[:size]):
                longest = size
                break
    return longest


@dataclass
class LeakedMarkupFilter:
    """Pass streamed text through until a leaked marker appears, then suppress the rest."""

    _held: str = field(default="", init=False)
    _leaked: bool = field(default=False, init=False)

    @property
    def leaked(self) -> bool:
        return self._leaked

    def push(self, text: str) -> str:
        if self._leaked or not text:
            return ""
        combined = self._held + text
        index = find_leaked_tool_markup(combined)
        if index is not None:
            self._leaked = True
            self._held = ""
            return combined[:index]
        keep = _pending_marker_prefix(combined)
        self._held = combined[len(combined) - keep :] if keep else ""
        return combined[: len(combined) - keep]

    def flush(self) -> str:
        held, self._held = self._held, ""
        return "" if self._leaked else held
