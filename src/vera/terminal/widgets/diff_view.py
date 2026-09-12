"""File-level Diff navigation over authoritative unified diffs."""

from __future__ import annotations

from dataclasses import dataclass

_MAX_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class DiffFile:
    path: str
    unified_diff: str


class DiffView:
    def __init__(self, files: tuple[DiffFile, ...], *, max_chars: int = _MAX_CHARS) -> None:
        self.files = files
        self.index = 0
        self.max_chars = max_chars

    @property
    def current(self) -> DiffFile | None:
        if not self.files:
            return None
        return self.files[self.index]

    def next_file(self) -> DiffFile | None:
        if not self.files:
            return None
        self.index = (self.index + 1) % len(self.files)
        return self.current

    def previous_file(self) -> DiffFile | None:
        if not self.files:
            return None
        self.index = (self.index - 1) % len(self.files)
        return self.current

    def visible_text(self) -> str:
        current = self.current
        if current is None:
            return "没有 Diff。"
        text = current.unified_diff
        numbered = _with_line_semantics(text)
        if len(numbered) > self.max_chars:
            return numbered[: self.max_chars] + "\n[truncated]"
        return numbered

    def copy_text(self) -> str:
        current = self.current
        if current is None:
            return ""
        return current.unified_diff

    def truncated(self) -> bool:
        current = self.current
        if current is None:
            return False
        return len(_with_line_semantics(current.unified_diff)) > self.max_chars


def _with_line_semantics(diff: str) -> str:
    lines: list[str] = []
    for index, line in enumerate(diff.splitlines(), start=1):
        mark = " "
        if line.startswith("+") and not line.startswith("+++"):
            mark = "+"
        elif line.startswith("-") and not line.startswith("---"):
            mark = "-"
        lines.append(f"{index:>4}{mark}{line}")
    return "\n".join(lines)


def files_from_payload(files: object) -> tuple[DiffFile, ...]:
    if not isinstance(files, list):
        return ()
    result: list[DiffFile] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        diff = item.get("unified_diff")
        if isinstance(path, str) and isinstance(diff, str):
            result.append(DiffFile(path=path, unified_diff=diff))
    return tuple(result)
