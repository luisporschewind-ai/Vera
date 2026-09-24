"""Visual-only animation clock for the status line."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic


class AnimationClock:
    _THINKING = ("·  ", "·· ", "···", "·· ")
    _REPLYING = ("▏  ", "▎  ", "▍  ", "▌  ")
    _WORKING = ("›··", "·›·", "··›")

    def __init__(
        self,
        *,
        enabled: bool = True,
        fps: int = 10,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if fps > 10:
            fps = 10
        self.enabled = enabled
        self.fps = max(1, fps)
        self._clock = clock or monotonic
        self._static = "•  "

    def wave_phase(self) -> float:
        if not self.enabled:
            return 0.0
        return (self._clock() * 0.4) % 1.0

    def frame(self, phase: str = "thinking") -> str:
        if not self.enabled:
            return self._static
        frames: tuple[str, ...]
        if phase == "thinking":
            frames = self._THINKING
            index = int(self._clock() * self.fps / 2) % len(frames)
        elif phase == "replying":
            frames = self._REPLYING
            index = int(self._clock() * self.fps) % len(frames)
        else:
            frames = self._WORKING
            index = int(self._clock() * self.fps) % len(frames)
        return frames[index]
