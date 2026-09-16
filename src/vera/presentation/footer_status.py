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
    activity_label: str
    activity_active: bool
    activity_severity: str
    unread: int = Field(ge=0)
    persist_label: str | None = None


def project_footer_status(
    session: SessionStatus,
    activity: ActivityState,
    *,
    unread: int = 0,
) -> FooterStatus:
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
        activity_label=activity.label,
        activity_active=activity.active,
        activity_severity=activity.severity,
        unread=max(0, unread),
        persist_label=persist,
    )


def context_bar(percent: int, cells: int, *, unicode: bool) -> str:
    filled = round(max(0, min(100, percent)) / 100 * cells)
    if unicode:
        return ("█" * filled) + ("░" * (cells - filled))
    return ("#" * filled) + ("." * (cells - filled))


def render_footer_status(
    footer: FooterStatus,
    *,
    columns: int,
    unicode: bool,
    frame: str,
) -> str:
    percent = footer.context_percent
    bar_cells = 8 if columns >= 80 else 6
    bar = context_bar(percent, bar_cells, unicode=unicode)
    left = f"会话上下文 {bar} {percent}%"
    if columns < 80:
        left = f"上下文 {bar} {percent}%"
    right = f"{footer.model_name}  推理 {footer.reasoning_label}"
    idle_mark = "✓" if footer.activity_severity == "info" else "!"
    if not unicode:
        idle_mark = "+" if footer.activity_severity == "info" else "!"
    marker = frame if footer.activity_active else idle_mark
    middle_bits = [f"{marker} {footer.activity_label}"]
    if footer.activity_active:
        middle_bits.append("Esc/Ctrl-C 取消")
    else:
        middle_bits.append("/help")
    if footer.unread:
        middle_bits.append(f"{footer.unread} 条新消息")
    if footer.persist_label:
        middle_bits.append(footer.persist_label)
    middle = " · ".join(middle_bits)
    if columns < 80:
        # Keep context percentage; drop model name. Keep reasoning if it still fits.
        right = f"推理 {footer.reasoning_label}"
        core = fit_left_right(left, right, columns)
        if display_width(core) > columns:
            return clip_display(left, columns)
        return core
    left_and_mid = f"{left}  {middle}"
    return fit_left_right(left_and_mid, right, columns)
