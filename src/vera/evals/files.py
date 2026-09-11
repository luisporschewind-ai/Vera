"""Capture workspace file facts without following links or saving content."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import NoReturn

from vera.evals.contracts import FileFact, FileKind


class FileInventoryError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.path = path
        self.message = message


def _fail(code: str, path: str, message: str) -> NoReturn:
    raise FileInventoryError(code, path, message)


class FileInventory:
    @staticmethod
    def capture(root: Path) -> tuple[FileFact, ...]:
        facts: list[FileFact] = []
        for path in _walk(root):
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                facts.append(FileFact(path=rel, kind=FileKind.DIRECTORY))
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            facts.append(
                FileFact(
                    path=rel,
                    kind=FileKind.FILE,
                    size=info.st_size,
                    sha256=digest.hexdigest(),
                )
            )
        return tuple(sorted(facts, key=lambda item: item.path))


def _walk(root: Path) -> tuple[Path, ...]:
    found: list[Path] = []

    def scan(current: Path) -> None:
        try:
            entries = list(os.scandir(current))
        except FileNotFoundError:
            _fail("missing_root", str(root), "workspace root does not exist")
        for entry in sorted(entries, key=lambda item: item.name):
            path = Path(entry.path)
            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                rel = path.relative_to(root).as_posix()
                _fail("special_file", rel, "workspace must not contain special files")
            if stat.S_ISDIR(mode):
                found.append(path)
                scan(path)
            else:
                found.append(path)

    scan(root)
    return tuple(found)
