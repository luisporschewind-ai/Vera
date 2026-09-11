"""Schedule UI-thread render flushes for streaming deltas."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic


class RenderScheduler:
    """Merge updates that arrive within interval_seconds."""

    def __init__(
        self,
        interval_seconds: float = 0.05,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._clock = clock or monotonic
        self._pending: dict[str, object] = {}
        self._last_flush = -interval_seconds

    def submit(self, key: str, value: object) -> bool:
        """Queue a value. Returns True if a flush should happen now."""

        self._pending[key] = value
        now = self._clock()
        return (now - self._last_flush) >= self.interval_seconds

    def flush(self) -> dict[str, object]:
        pending = dict(self._pending)
        self._pending.clear()
        self._last_flush = self._clock()
        return pending

    @property
    def pending_count(self) -> int:
        return len(self._pending)
