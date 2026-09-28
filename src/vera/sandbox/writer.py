"""Atomic writes held to an authorized directory descriptor."""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

from vera.sandbox.access import ResourceIdentity
from vera.sandbox.files import PermissionPaths
from vera.workspace.paths import WorkspaceBoundaryError


class PermissionFileWriter:
    def __init__(self, paths: PermissionPaths) -> None:
        self.paths = paths

    @contextmanager
    def _parent(self, path: Path) -> Iterator[int]:
        canonical = self.paths._authorize(path, "write")
        if canonical != path:
            raise WorkspaceBoundaryError("write target changed", code="fact_mismatch")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open("/", flags)
        try:
            for component in path.parent.parts[1:]:
                child = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            current = path.parent.stat()
            opened = os.fstat(fd)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise WorkspaceBoundaryError("parent changed", code="fact_mismatch")
            self.paths._authorize(path, "write")
            try:
                target = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                target = None
            if target is not None and not stat.S_ISREG(target.st_mode):
                raise WorkspaceBoundaryError("regular file required", code="special_file")
            yield fd
        finally:
            os.close(fd)

    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
        with self._parent(path) as parent:
            previous = ResourceIdentity.capture(path)
            temporary = f".vera-write-{uuid4().hex}"
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    if mode is not None:
                        os.fchmod(stream.fileno(), mode)
                    os.fsync(stream.fileno())
                    info = os.fstat(stream.fileno())
                self.paths._authorize(path, "write")
                os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                self.paths.session.record_core_replacement(
                    path,
                    previous,
                    ResourceIdentity(path, info.st_dev, info.st_ino, False, path, True),
                )
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(temporary, dir_fd=parent)

    def delete(self, path: Path) -> None:
        with self._parent(path) as parent, suppress(FileNotFoundError):
            os.unlink(path.name, dir_fd=parent)
