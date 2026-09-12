"""In-process prompt history. Never written to disk."""

from __future__ import annotations


class PromptHistory:
    def __init__(self, *, limit: int = 100) -> None:
        self.limit = limit
        self._items: list[str] = []
        self._index: int | None = None
        self._draft: str | None = None

    def __len__(self) -> int:
        return len(self._items)

    def record(self, text: str) -> None:
        cleaned = text.rstrip("\n")
        if not cleaned.strip():
            return
        if self._items and self._items[-1] == cleaned:
            self.reset_cursor()
            return
        self._items.append(cleaned)
        if len(self._items) > self.limit:
            self._items = self._items[-self.limit :]
        self.reset_cursor()

    def up(self, current: str) -> str:
        if not self._items:
            return current
        if self._index is None:
            self._draft = current
            self._index = len(self._items) - 1
        elif self._index > 0:
            self._index -= 1
        return self._items[self._index]

    def down(self) -> str:
        if self._index is None:
            return self._draft if self._draft is not None else ""
        if self._index < len(self._items) - 1:
            self._index += 1
            return self._items[self._index]
        draft = self._draft if self._draft is not None else ""
        self.reset_cursor()
        return draft

    def search(self, query: str) -> tuple[str, ...]:
        if not query:
            return ()
        return tuple(item for item in reversed(self._items) if query in item)

    def browsing(self) -> bool:
        return self._index is not None

    def reset_cursor(self) -> None:
        self._index = None
        self._draft = None

    def clear(self) -> None:
        self._items.clear()
        self.reset_cursor()
