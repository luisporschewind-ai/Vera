"""Atomic private-file writes that never chmod caller-owned parents."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
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
    def fsync_directory(self, path: Path) -> None:
        path = Path(path)
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

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


class PrivateAppendWriter:
    """Append one complete JSONL line with private permissions and fsync."""

    def __init__(self) -> None:
        self._atomic = PrivateAtomicWriter()

    def append_line(self, path: Path, data: bytes) -> None:
        path = Path(path)
        parent = path.parent
        if parent.is_symlink():
            _fail("symlink_target", parent, "refusing to append through a parent symlink")
        if path.is_symlink():
            _fail("symlink_target", path, "refusing to append through a symlink")
        if path.exists() and not path.is_file():
            _fail("not_a_file", path, "append target is not a regular file")
        self._atomic.ensure_directory(parent)
        line = data if data.endswith(b"\n") else data + b"\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            flags |= nofollow
        fd = -1
        original_size = path.stat().st_size if path.exists() else 0
        try:
            fd = os.open(path, flags, 0o600)
            os.fchmod(fd, 0o600)
            original_size = os.fstat(fd).st_size
            written = os.write(fd, line)
            if written != len(line):
                os.ftruncate(fd, original_size)
                _fail("short_write", path, "append did not write the complete line")
            os.fsync(fd)
        except PrivateWriteError:
            raise
        except OSError as exc:
            if fd >= 0:
                with suppress(OSError):
                    os.ftruncate(fd, original_size)
            _fail("write_failed", path, str(exc))
        finally:
            if fd >= 0:
                os.close(fd)
