"""Workspace-bounded @path candidates. Mentions are not approvals."""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_IGNORED_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".vera",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)
_MAX_DIR_ENTRIES = 200
_DEFAULT_LIMIT = 40


@dataclass(frozen=True, slots=True)
class PathMention:
    display: str
    relative_path: str
    kind: Literal["file", "directory"]


def suggest_path_mentions(
    workspace: Path,
    prefix: str,
    *,
    limit: int = _DEFAULT_LIMIT,
    state_dir: Path | None = None,
) -> tuple[PathMention, ...]:
    root = workspace.resolve()
    if not root.is_dir():
        return ()
    state_root = state_dir.resolve() if state_dir is not None else None
    ignore_patterns = _gitignore_patterns(root)
    needle = prefix.replace("\\", "/").lstrip("./")
    matches: list[PathMention] = []
    _walk(root, root, needle, ignore_patterns, state_root, matches, limit)
    return tuple(matches)


def _walk(
    root: Path,
    current: Path,
    needle: str,
    ignore_patterns: tuple[str, ...],
    state_root: Path | None,
    matches: list[PathMention],
    limit: int,
) -> None:
    if len(matches) >= limit:
        return
    try:
        entries = list(os.scandir(current))
    except OSError:
        return
    if len(entries) > _MAX_DIR_ENTRIES:
        entries = entries[:_MAX_DIR_ENTRIES]
    for entry in entries:
        if len(matches) >= limit:
            return
        name = entry.name
        if name in _IGNORED_NAMES or name.startswith("."):
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode):
            continue
        path = Path(entry.path)
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if state_root is not None:
            try:
                path.resolve(strict=False).relative_to(state_root)
            except ValueError:
                pass
            else:
                continue
        if _ignored(relative, name, ignore_patterns):
            continue
        if stat.S_ISDIR(info.st_mode):
            mention = PathMention(display=relative, relative_path=relative, kind="directory")
            if _matches(relative, name, needle):
                matches.append(mention)
            _walk(root, path, needle, ignore_patterns, state_root, matches, limit)
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if _matches(relative, name, needle):
            matches.append(PathMention(display=relative, relative_path=relative, kind="file"))


def _matches(relative: str, name: str, needle: str) -> bool:
    if not needle:
        return True
    return relative.casefold().startswith(needle.casefold()) or name.casefold().startswith(
        needle.casefold()
    )


def _gitignore_patterns(root: Path) -> tuple[str, ...]:
    source = root / ".gitignore"
    if not source.is_file() or source.is_symlink():
        return ()
    patterns: list[str] = []
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line.rstrip("/"))
    return tuple(patterns)


def _ignored(relative: str, name: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative, pattern):
            return True
        if fnmatch.fnmatch(relative, f"**/{pattern}"):
            return True
    return False
