"""Session-only built-in themes. No file writes and no executable theme code."""

from __future__ import annotations

from typing import Literal

from textual.theme import Theme

ThemeName = Literal["default", "high-contrast", "no-color"]
THEME_NAMES: tuple[ThemeName, ...] = ("default", "high-contrast", "no-color")
THEME_CHOICES: tuple[tuple[ThemeName, str], ...] = (
    ("default", "默认"),
    ("high-contrast", "高对比"),
    ("no-color", "无色"),
)

VERA_THEMES: tuple[Theme, ...] = (
    Theme(
        name="default",
        primary="#1B4F8A",
        secondary="#0F2C4C",
        accent="#2A5F9E",
        warning="#C4A35A",
        error="#ba3c5b",
        success="#4EBF71",
        foreground="#e0e0e0",
        background="#121212",
        surface="#121212",
        dark=True,
    ),
    Theme(
        name="high-contrast",
        primary="#ffff00",
        secondary="#00ffff",
        accent="#ffff00",
        warning="#ffff00",
        error="#ff4444",
        success="#00ff00",
        foreground="#ffffff",
        background="#000000",
        surface="#000000",
        panel="#000000",
        boost="#000000",
        dark=True,
    ),
    Theme(
        name="no-color",
        primary="#9a9a9a",
        secondary="#7a7a7a",
        accent="#b0b0b0",
        warning="#c8c8c8",
        error="#e0e0e0",
        success="#b8b8b8",
        foreground="#e0e0e0",
        background="#1a1a1a",
        surface="#2a2a2a",
        panel="#222222",
        boost="#202020",
        dark=True,
    ),
)


def normalize_theme(name: str | None, current: ThemeName = "default") -> ThemeName | None:
    if name is None or name == "":
        return current
    candidate = name.strip().lower()
    for item in THEME_NAMES:
        if candidate == item:
            return item
    return None


def matching_themes(prefix: str) -> tuple[tuple[ThemeName, str], ...]:
    needle = prefix.strip().lower()
    return tuple((name, label) for name, label in THEME_CHOICES if name.startswith(needle))


def theme_class(name: ThemeName) -> str:
    return f"theme-{name}"


def format_theme_status(name: str) -> str:
    labels: dict[str, str] = {item: label for item, label in THEME_CHOICES}
    current = labels.get(name, name)
    available = ", ".join(f"{item}（{labels[item]}）" for item in THEME_NAMES)
    return f"当前主题：{name}（{current}）\n可用：{available}"
