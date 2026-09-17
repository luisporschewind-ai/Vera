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

TOKEN_NAMES: tuple[str, ...] = (
    "background",
    "surface",
    "surface_elevated",
    "text_primary",
    "text_muted",
    "accent",
    "success",
    "warning",
    "danger",
    "focus",
    "diff_add",
    "diff_remove",
)

SEMANTIC_TOKENS: dict[ThemeName, dict[str, str]] = {
    "default": {
        "background": "#0B1C28",
        "surface": "#122433",
        "surface_elevated": "#1A3144",
        "text_primary": "#D7E4EE",
        "text_muted": "#7E96A8",
        "accent": "#3D7A8C",
        "success": "#4A8B6F",
        "warning": "#B08A4A",
        "danger": "#A85A5A",
        "focus": "#5B9BB0",
        "diff_add": "#3D6B55",
        "diff_remove": "#8B4A4A",
    },
    "high-contrast": {
        "background": "#000000",
        "surface": "#000000",
        "surface_elevated": "#000000",
        "text_primary": "#FFFFFF",
        "text_muted": "#FFFFFF",
        "accent": "#FFFF00",
        "success": "#00FF00",
        "warning": "#FFFF00",
        "danger": "#FF4444",
        "focus": "#FFFF00",
        "diff_add": "#00FF00",
        "diff_remove": "#FF4444",
    },
    "no-color": {
        "background": "#1A1A1A",
        "surface": "#2A2A2A",
        "surface_elevated": "#222222",
        "text_primary": "#E0E0E0",
        "text_muted": "#B0B0B0",
        "accent": "#B0B0B0",
        "success": "#C8C8C8",
        "warning": "#D0D0D0",
        "danger": "#E0E0E0",
        "focus": "#F0F0F0",
        "diff_add": "#E0E0E0",
        "diff_remove": "#E0E0E0",
    },
}


def _theme(name: ThemeName) -> Theme:
    tokens = SEMANTIC_TOKENS[name]
    return Theme(
        name=name,
        primary=tokens["accent"],
        secondary=tokens["surface"],
        accent=tokens["accent"],
        warning=tokens["warning"],
        error=tokens["danger"],
        success=tokens["success"],
        foreground=tokens["text_primary"],
        background=tokens["background"],
        surface=tokens["surface"],
        panel=tokens["surface_elevated"],
        boost=tokens["surface_elevated"],
        dark=True,
    )


VERA_THEMES: tuple[Theme, ...] = (
    _theme("default"),
    _theme("high-contrast"),
    _theme("no-color"),
)


def semantic_tokens(name: ThemeName) -> dict[str, str]:
    return dict(SEMANTIC_TOKENS[name])


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
