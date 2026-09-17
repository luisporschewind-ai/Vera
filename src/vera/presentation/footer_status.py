"""UI-independent footer status projection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.presentation.activity import ActivityState
from vera.session.models import SessionStatus
from vera.terminal.display import clip_display, display_width, fit_left_right


class FooterStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_used: int = Field(ge=0)
    context_max: int = Field(ge=1)
    context_ratio: float
    context_percent: int = Field(ge=0, le=100)
    context_warning: bool
    model_profile: str
    model_name: str
    reasoning_mode: Literal["explicit", "provider_default", "unavailable"]
    reasoning_label: str
    unread: int = Field(ge=0)
    persist_label: str | None = None


def project_footer_status(
    session: SessionStatus,
    activity: ActivityState | None = None,
    *,
    unread: int = 0,
) -> FooterStatus:
    del activity
    used = session.context.context_bytes
    maximum = session.context.max_bytes
    ratio = min(1.0, used / maximum) if maximum else 0.0
    percent = min(100, round(ratio * 100))
    persist = None
    if session.context.persistent_state == "unsaved":
        persist = "未保存"
    return FooterStatus(
        context_used=used,
        context_max=maximum,
        context_ratio=ratio,
        context_percent=percent,
        context_warning=session.context.warning or percent >= 100,
        model_profile=session.model_profile,
        model_name=session.model_name,
        reasoning_mode=session.reasoning.mode,
        reasoning_label=session.reasoning.display_label(),
        unread=max(0, unread),
        persist_label=persist,
    )


def context_bar(percent: int, cells: int, *, unicode: bool, used: int = 0) -> str:
    filled = round(max(0, min(100, percent)) / 100 * cells)
    if used > 0 and filled == 0:
        filled = 1
    if unicode:
        return ("█" * filled) + ("░" * (cells - filled))
    return ("#" * filled) + ("." * (cells - filled))


def format_context_k(n: int) -> str:
    """Render a byte count as K once it reaches 1000."""

    if n < 1000:
        return str(n)
    kilos = n / 1000
    if kilos == int(kilos):
        return f"{int(kilos)}K"
    return f"{kilos:.1f}K"


def _left_candidates(
    footer: FooterStatus, context_full: str, context_short: str, occupancy: str
) -> tuple[str, ...]:
    prefixes: list[str] = []
    if footer.persist_label:
        prefixes.append(footer.persist_label)
    if footer.unread:
        prefixes.append(f"{footer.unread} 条新消息")
    extras = [" · ".join(prefixes[:keep]) for keep in range(len(prefixes), 0, -1)]
    bases = (context_full, context_short, occupancy)
    ordered: list[str] = []
    for extra in extras:
        for base in bases:
            ordered.append(f"{extra}  {base}")
    ordered.extend(bases)
    return tuple(ordered)


def _fits_footer(left: str, right: str, columns: int) -> bool:
    right_width = display_width(right)
    if right_width >= columns:
        return False
    return display_width(left) <= columns - right_width - 1


def render_footer_status(
    footer: FooterStatus,
    *,
    columns: int,
    unicode: bool,
    frame: str = "·",
) -> str:
    del frame
    occupancy = f"{format_context_k(footer.context_used)}/{format_context_k(footer.context_max)}"
    bar_cells = 8 if columns >= 80 else 6
    bar = context_bar(footer.context_percent, bar_cells, unicode=unicode, used=footer.context_used)
    context_full = f"会话上下文 {bar} {occupancy}"
    context_short = f"上下文 {bar} {occupancy}"
    lefts = _left_candidates(footer, context_full, context_short, occupancy)
    if columns < 80:
        right = f"推理 {footer.reasoning_label}"
        for left in lefts:
            if _fits_footer(left, right, columns):
                return fit_left_right(left, right, columns)
        return clip_display(lefts[-1], columns)
    right = f"{footer.model_name}  推理 {footer.reasoning_label}"
    for left in lefts:
        if _fits_footer(left, right, columns):
            return fit_left_right(left, right, columns)
    return clip_display(lefts[-1], columns)
