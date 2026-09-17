"""UI-independent work-rail projection above the composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from vera.presentation.activity import ActivityState
from vera.terminal.display import clip_display


class WorkRailStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    visible: bool
    label: str
    target: str = ""
    steps: tuple[str, ...] = ()
    active: bool
    severity: str
    cancel_hint: bool = False


def project_work_rail(activity: ActivityState) -> WorkRailStatus:
    idle_done = activity.label in {"就绪", "已完成", "已取消"} and not activity.active
    visible = (activity.active or activity.severity == "error") and not idle_done
    return WorkRailStatus(
        visible=visible,
        label=activity.label,
        target=activity.target,
        steps=activity.steps,
        active=activity.active,
        severity=activity.severity,
        cancel_hint=activity.active,
    )


def render_work_rail(
    rail: WorkRailStatus,
    *,
    columns: int,
    unicode: bool,
    frame: str,
) -> str:
    del unicode
    if not rail.visible:
        return ""
    marker = frame if rail.active else "!"
    line = f"{marker} {rail.label}"
    if rail.target:
        line = f"{line}  {rail.target}"
    steps = " → ".join(rail.steps)
    if columns < 80:
        extra = " · Esc/Ctrl-C 取消" if rail.cancel_hint else ""
        return clip_display(f"{line}{extra}", columns)
    second_parts = [part for part in (steps, "Esc/Ctrl-C 取消" if rail.cancel_hint else "") if part]
    if not second_parts:
        return clip_display(line, columns)
    second = " · ".join(second_parts)
    width = max(4, columns)
    return f"{clip_display(line, width)}\n{clip_display(second, width)}"
