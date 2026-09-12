"""Session-only built-in themes. No file writes and no executable theme code."""

from __future__ import annotations

from typing import Literal

ThemeName = Literal["default", "high-contrast", "no-color"]
THEME_NAMES: tuple[ThemeName, ...] = ("default", "high-contrast", "no-color")


def normalize_theme(name: str | None, current: ThemeName = "default") -> ThemeName | None:
    if name is None or name == "":
        return current
    candidate = name.strip().lower()
    for item in THEME_NAMES:
        if candidate == item:
            return item
    return None


def theme_class(name: ThemeName) -> str:
    return f"theme-{name}"
