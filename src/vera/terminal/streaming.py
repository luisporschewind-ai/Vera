"""Bounded stream refresh rates for timeline updates."""

from __future__ import annotations

from vera.terminal.render_scheduler import RenderScheduler

MAX_STREAM_FPS = 20
MAX_ANIMATION_FPS = 10


def stream_interval_seconds(fps: int = MAX_STREAM_FPS) -> float:
    bounded = max(1, min(fps, MAX_STREAM_FPS))
    return 1.0 / bounded


def animation_interval_seconds(fps: int = MAX_ANIMATION_FPS) -> float:
    bounded = max(1, min(fps, MAX_ANIMATION_FPS))
    return 1.0 / bounded


def bounded_scheduler(fps: int = MAX_STREAM_FPS) -> RenderScheduler:
    return RenderScheduler(interval_seconds=stream_interval_seconds(fps))
