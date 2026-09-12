"""Atomic private-file writes that never chmod caller-owned parents."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import NoReturn


class PrivateWriteError(ValueError):
    def __init__(self, code: str, path: Path | str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.path = Path(path)
        self.message = message


def _fail(code: str, path: Path | str, message: str) -> NoReturn:
    raise PrivateWriteError(code, path, message)


class PrivateAtomicWriter:
    def ensure_directory(self, path: Path) -> None:
        path = Path(path)
        if path.exists():
            if path.is_symlink() or not path.is_dir():
                _fail("not_a_directory", path, "private directory target is not a directory")
            return
        missing: list[Path] = []
        current = path
        while not current.exists():
            missing.append(current)
            parent = current.parent
            if parent == current:
                _fail("not_a_directory", path, "cannot create private directory")
            current = parent
        if current.is_symlink() or not current.is_dir():
            _fail("not_a_directory", current, "private directory parent is not a directory")
        for item in reversed(missing):
            try:
                os.mkdir(item, 0o700)
            except FileExistsError:
                if item.is_symlink() or not item.is_dir():
                    _fail("not_a_directory", item, "private directory target is not a directory")

    def write_bytes(self, path: Path, data: bytes) -> None:
        path = Path(path)
        if path.is_symlink():
            _fail("symlink_target", path, "refusing to write through a symlink")
        if path.exists():
            _fail("target_exists", path, "private write refuses to overwrite an existing file")
        self.ensure_directory(path.parent)
        fd = -1
        temporary: Path | None = None
        try:
            fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            temporary = Path(temporary_name)
            os.fchmod(fd, 0o600)
            written = 0
            view = memoryview(data)
            while written < len(data):
                written += os.write(fd, view[written:])
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.link(temporary, path)
            temporary.unlink()
            temporary = None
        except PrivateWriteError:
            raise
        except OSError as exc:
            _fail("write_failed", path, str(exc))
        finally:
            if fd >= 0:
                os.close(fd)
            if temporary is not None:
                temporary.unlink(missing_ok=True)
