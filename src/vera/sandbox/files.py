"""Permission-aware file paths; checks precede content inspection."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from vera.sandbox.access import (
    AccessDenied,
    AccessSession,
    FileOperation,
    FilePermissions,
    ResourceIdentity,
)
from vera.workspace.paths import FileKind, PathFact, WorkspaceBoundaryError, WorkspacePaths


def read_descriptor(
    path: Path, *, limit: int | None = None, validate: Callable[[], object] | None = None
) -> bytes:
    """Walk canonical components without following any replacement symlinks."""
    flags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open("/", flags | os.O_DIRECTORY)
    try:
        for index, part in enumerate(path.parts[1:]):
            last = index == len(path.parts) - 2
            child = os.open(part, flags | (os.O_NONBLOCK if last else os.O_DIRECTORY), dir_fd=fd)
            os.close(fd)
            fd = child
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise WorkspaceBoundaryError("regular file required", code="special_file")
        current = os.stat(path, follow_symlinks=False)
        opened = os.fstat(fd)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise WorkspaceBoundaryError("file changed", code="fact_mismatch")
        if validate is not None:
            validate()
        with os.fdopen(os.dup(fd), "rb") as stream:
            return stream.read() if limit is None else stream.read(limit)
    finally:
        os.close(fd)


_ACTIVE: ContextVar[tuple[AccessSession, FilePermissions, tuple[ResourceIdentity, ...]] | None] = (
    ContextVar("vera_file_access", default=None)
)


def operation_key(name: str, arguments: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"tool": name, "arguments": arguments}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def current_permissions(session: AccessSession) -> FilePermissions | None:
    active = _ACTIVE.get()
    return active[1] if active is not None and active[0] is session else None


@contextmanager
def file_operation(
    session: AccessSession, name: str, arguments: dict[str, object], *, consume: bool
) -> Iterator[None]:
    active = _ACTIVE.get()
    if active is not None and active[0] is session:
        yield
        return
    raw = arguments.get("path")
    key = operation_key(name, arguments)
    resources: tuple[tuple[Path, FileOperation], ...]
    if name in {
        "read",
        "ls",
        "grep",
        "find",
        "write",
        "edit",
        "read_file",
        "list_directory",
        "search_text",
    } and isinstance(raw, str):
        mode: FileOperation = "write" if name in {"write", "edit"} else "read"
        resources = ((Path(raw), mode),)
    else:
        resources = session.command_resources(key)
    with session.operation(key, resources, consume=consume) as permissions:
        permissions.validate()
        identities = permissions.identities
        token = _ACTIVE.set((session, permissions, identities))
        try:
            yield
        finally:
            _ACTIVE.reset(token)


class PermissionPaths(WorkspacePaths):
    def __init__(self, session: AccessSession) -> None:
        super().__init__(session.workspace)
        self.session = session

    @staticmethod
    def _relative(raw_path: str) -> Path:
        if not raw_path or not raw_path.strip() or "\x00" in raw_path:
            raise WorkspaceBoundaryError("invalid path", code="empty_path")
        return Path(raw_path)

    def _authorize(self, candidate: Path, mode: FileOperation) -> Path:
        try:
            canonical = self.session.canonical(candidate)
            active = _ACTIVE.get()
            if active is not None and active[0] is self.session:
                _, permissions, identities = active
                if permissions.revoked.is_set():
                    raise AccessDenied("permission_revoked")
                for identity in identities:
                    identity.validate()
                roots = permissions.writable if mode == "write" else permissions.readable
                if not any(
                    canonical == root or (identity.is_directory and root in canonical.parents)
                    for root in roots
                    for identity in identities
                    if identity.target == root
                ):
                    raise AccessDenied("file_access_approval_required")
            else:
                with self.session.operation("file", ((canonical, mode),), consume=False):
                    pass
            if self.protected.is_protected(canonical):
                raise AccessDenied("protected_path")
            return canonical
        except AccessDenied as exc:
            raise WorkspaceBoundaryError(str(exc), code=str(exc)) from exc

    def _within_root(self, candidate: Path) -> Path:
        return self._authorize(candidate, "read")

    def inspect_read(self, raw_path: str) -> PathFact:
        self._authorize(self.root / self._relative(raw_path), "read")
        return super().inspect_read(raw_path)

    def inspect_mutation(self, raw_path: str) -> PathFact:
        target = self._authorize(self.root / self._relative(raw_path), "write")
        # Inspect a canonical target without expanding its parent's permission.
        relative = self._relative(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            if target.exists() and not target.is_file():
                raise WorkspaceBoundaryError("regular file required", code="special_file")
            return self._fact_from_lstat(Path(str(target)), target, follow_final=False)
        return super().inspect_mutation(raw_path)

    def _content_hash(self, path: Path, kind: FileKind) -> str | None:
        if kind != "regular":
            return None
        target = self._authorize(path, "read")
        return hashlib.sha256(
            read_descriptor(target, validate=lambda: self._authorize(target, "read"))
        ).hexdigest()

    def read_bytes(self, raw_path: str, limit: int | None = None) -> bytes:
        target = self._authorize(self.root / self._relative(raw_path), "read")
        return read_descriptor(
            target, limit=limit, validate=lambda: self._authorize(target, "read")
        )

    @contextmanager
    def _directory(self, target: Path) -> Iterator[int]:
        target = self._authorize(target, "read")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open("/", flags)
        try:
            for part in target.parts[1:]:
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            self._authorize(target, "read")
            current = target.stat()
            opened = os.fstat(fd)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise WorkspaceBoundaryError("directory changed", code="fact_mismatch")
            yield fd
        finally:
            os.close(fd)

    def list_names(self, raw_path: str) -> list[str]:
        with self._directory(self.root / self._relative(raw_path)) as fd:
            return os.listdir(fd)

    def iter_files(self, raw_path: str, pattern: str = "*") -> Iterator[Path]:
        pending = [self._authorize(self.root / self._relative(raw_path), "read")]
        ignored = {".git", ".venv", "node_modules", "dist", "build", ".vera"}
        while pending:
            directory = pending.pop()
            try:
                with self._directory(directory) as fd, os.scandir(fd) as entries:
                    for entry in entries:
                        path = directory / entry.name
                        if entry.is_symlink() or entry.name in ignored:
                            continue
                        try:
                            self._authorize(path, "read")
                        except WorkspaceBoundaryError:
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(path)
                        elif entry.is_file(follow_symlinks=False) and path.match(pattern):
                            yield path
            except (OSError, WorkspaceBoundaryError):
                continue
