"""Vera CLI wordmark selection. No Nerd Font, emoji, or geometric mark."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.terminal.display import clip_display

BrandMode = Literal["full", "compact", "ascii"]
_WORDMARK = "VERA"
_ACCESSIBLE = "Vera"


class BrandMark(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: BrandMode
    lines: tuple[str, ...] = Field(min_length=1, max_length=2)
    accessible_label: str = _ACCESSIBLE


def select_brand_mark(
    *,
    columns: int,
    rows: int,
    unicode: bool,
    no_color: bool,
) -> BrandMark:
    del no_color
    budget = max(0, columns)
    word = clip_display(_WORDMARK, budget)
    if not unicode:
        mode: BrandMode = "ascii"
    elif columns >= 80 and rows >= 24:
        mode = "full"
    else:
        mode = "compact"
    return BrandMark(mode=mode, lines=(word,), accessible_label=_ACCESSIBLE)
