"""Terminal display-width helpers. CJK and fullwidth count as two columns."""

from __future__ import annotations

import unicodedata


def cell_width(char: str) -> int:
    if not char or char in "\n\r":
        return 0
    east_asian = unicodedata.east_asian_width(char)
    if east_asian in {"F", "W"}:
        return 2
    return 1


def display_width(text: str) -> int:
    return sum(cell_width(char) for char in text)


def clip_display(text: str, columns: int) -> str:
    if columns <= 0:
        return ""
    out: list[str] = []
    used = 0
    for char in text:
        width = cell_width(char)
        if used + width > columns:
            break
        out.append(char)
        used += width
    return "".join(out)


def pad_display(text: str, columns: int) -> str:
    clipped = clip_display(text, columns)
    return clipped + (" " * (columns - display_width(clipped)))


def fit_left_right(left: str, right: str, columns: int) -> str:
    right_width = display_width(right)
    if right_width >= columns:
        return clip_display(right, columns)
    left_budget = columns - right_width - 1
    left_part = clip_display(left, max(0, left_budget)).rstrip()
    pad = columns - display_width(left_part) - right_width
    if pad < 1:
        left_part = clip_display(left, columns - right_width - 1).rstrip()
        pad = columns - display_width(left_part) - right_width
    return left_part + (" " * pad) + right
