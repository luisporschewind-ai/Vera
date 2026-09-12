"""Conservative terminal capability detection for color and animation."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DisplayCapabilities:
    tty: bool
    color: bool
    animations: bool
    term: str
    reduced_motion: bool


def detect_display_capabilities(
    environ: Mapping[str, str] | None = None,
    *,
    stdout_tty: bool | None = None,
    animations_config: bool = True,
) -> DisplayCapabilities:
    env = os.environ if environ is None else environ
    term = str(env.get("TERM", "") or "")
    tty = sys.stdout.isatty() if stdout_tty is None else stdout_tty
    no_color = env.get("NO_COLOR", "") != "" or term.strip().lower() in {"", "dumb"}
    reduced = env.get("VERA_NO_ANIMATIONS", "") == "1" or not animations_config
    color = bool(tty and not no_color)
    animations = bool(tty and color and not reduced)
    return DisplayCapabilities(
        tty=tty,
        color=color,
        animations=animations,
        term=term or "unavailable",
        reduced_motion=reduced or not animations,
    )
