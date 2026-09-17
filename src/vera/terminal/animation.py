"""Visual-only animation clock for the status line."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic


class AnimationClock:
    _FRAMES = ("◐", "◓", "◑", "◒")

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
        self._static = "●"

    def wave_phase(self) -> float:
        if not self.enabled:
            return 0.0
        return (self._clock() * 0.22) % 1.0

    def frame(self) -> str:
        if not self.enabled:
            return self._static
        index = int(self._clock() * self.fps) % len(self._FRAMES)
        return self._FRAMES[index]
