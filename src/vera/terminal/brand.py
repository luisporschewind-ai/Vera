"""Vera CLI wordmark selection. No Nerd Font, emoji, or geometric mark."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.terminal.display import clip_display

BrandMode = Literal["full", "compact", "ascii"]
_WORDMARK = "VERA"
_ACCESSIBLE = "Vera"
_DENSE_UNICODE = (
    "⢿⡀ ⢀⡿ ⣿⠛⠛⠛ ⣿⠛⠛⢳ ⢀⡞⢳⡀",
    "⠈⢷⣀⡾⠁ ⣿⠛⠛  ⣿⠛⢿⡁ ⣸⠗⠺⣇",
    " ⠈⣿⠁  ⠿⠶⠶⠶ ⠿  ⠿ ⠿  ⠿",
)
_DENSE_ASCII = (
    ".. .. .... .... ....",
    "..... ...  .... ....",
    " ...  .... .  . .  .",
)


class BrandMark(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: BrandMode
    lines: tuple[str, ...] = Field(min_length=1, max_length=3)
    accessible_label: str = _ACCESSIBLE


def select_brand_mark(
    *,
    columns: int,
    rows: int,
    unicode: bool,
    no_color: bool,
    expanded: bool = True,
) -> BrandMark:
    del no_color, rows
    budget = max(0, columns)
    if not expanded:
        mode: BrandMode = "ascii" if not unicode else "compact"
        return BrandMark(
            mode=mode,
            lines=(clip_display(_WORDMARK, budget),),
            accessible_label=_ACCESSIBLE,
        )
    source = _DENSE_UNICODE if unicode else _DENSE_ASCII
    mode = "full" if unicode else "ascii"
    return BrandMark(
        mode=mode,
        lines=tuple(clip_display(line, budget) for line in source),
        accessible_label=_ACCESSIBLE,
    )
