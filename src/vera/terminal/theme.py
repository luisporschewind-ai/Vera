"""Session-only built-in themes. No file writes and no executable theme code."""

from __future__ import annotations

from typing import Literal

from textual.theme import Theme

ThemeName = Literal["default", "light", "cream", "high-contrast", "no-color"]
THEME_NAMES: tuple[ThemeName, ...] = ("default", "light", "cream", "high-contrast", "no-color")
THEME_CHOICES: tuple[tuple[ThemeName, str], ...] = (
    ("default", "默认"),
    ("light", "Light"),
    ("cream", "奶油"),
    ("high-contrast", "高对比"),
    ("no-color", "无色"),
)

TOKEN_NAMES: tuple[str, ...] = (
    "background",
    "surface",
    "surface_elevated",
    "user_surface",
    "text_primary",
    "text_muted",
    "accent",
    "logo",
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
        "user_surface": "#29485B",
        "text_primary": "#D7E4EE",
        "text_muted": "#7E96A8",
        "accent": "#3D7A8C",
        "logo": "#548EA0",
        "success": "#4A8B6F",
        "warning": "#B08A4A",
        "danger": "#A85A5A",
        "focus": "#5B9BB0",
        "diff_add": "#3D6B55",
        "diff_remove": "#8B4A4A",
    },
    "light": {
        "background": "#F3F6F9",
        "surface": "#FFFFFF",
        "surface_elevated": "#E7EEF3",
        "user_surface": "#AFC9D9",
        "text_primary": "#1A2B36",
        "text_muted": "#5A7180",
        "accent": "#2F6F82",
        "logo": "#2F6F82",
        "success": "#2F6B4F",
        "warning": "#9A6B1F",
        "danger": "#A63D3D",
        "focus": "#2F6F82",
        "diff_add": "#2F6B4F",
        "diff_remove": "#A63D3D",
    },
    "cream": {
        "background": "#FBF6EC",
        "surface": "#FFFCF5",
        "surface_elevated": "#F3E8D4",
        "user_surface": "#DFC38D",
        "text_primary": "#3D3429",
        "text_muted": "#7A6E5F",
        "accent": "#C4843A",
        "logo": "#C4843A",
        "success": "#5A7A4A",
        "warning": "#C49A3A",
        "danger": "#B85A45",
        "focus": "#D4923F",
        "diff_add": "#5A7A4A",
        "diff_remove": "#B85A45",
    },
    "high-contrast": {
        "background": "#000000",
        "surface": "#000000",
        "surface_elevated": "#000000",
        "user_surface": "#FFFFFF",
        "text_primary": "#FFFFFF",
        "text_muted": "#FFFFFF",
        "accent": "#FFFF00",
        "logo": "#FFFF00",
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
        "user_surface": "#4A4A4A",
        "text_primary": "#E0E0E0",
        "text_muted": "#B0B0B0",
        "accent": "#B0B0B0",
        "logo": "#B0B0B0",
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
        dark=name not in {"light", "cream"},
        variables={"logo": tokens["logo"], "user-surface": tokens["user_surface"]},
    )


VERA_THEMES: tuple[Theme, ...] = (
    _theme("default"),
    _theme("light"),
    _theme("cream"),
    _theme("high-contrast"),
    _theme("no-color"),
)


def semantic_tokens(name: ThemeName) -> dict[str, str]:
    return dict(SEMANTIC_TOKENS[name])


def normalize_theme(name: str | None, current: ThemeName = "default") -> ThemeName | None:
    if name is None or name == "":
        return current
    candidate = name.strip().lower()
    for item, label in THEME_CHOICES:
        if candidate == item or candidate == label.lower():
            return item
    return None


def matching_themes(prefix: str) -> tuple[tuple[ThemeName, str], ...]:
    needle = prefix.strip().lower()
    return tuple(
        (name, label)
        for name, label in THEME_CHOICES
        if name.startswith(needle) or label.lower().startswith(needle)
    )


def theme_class(name: ThemeName) -> str:
    return f"theme-{name}"


def format_theme_status(name: str) -> str:
    labels: dict[str, str] = {item: label for item, label in THEME_CHOICES}
    current = labels.get(name, name)
    available = ", ".join(f"{item}（{labels[item]}）" for item in THEME_NAMES)
    return f"当前主题：{name}（{current}）\n可用：{available}"
