"""Resolve workspace-relative paths without allowing boundary escapes."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from vera.contracts import ContractModel

FileKind = Literal[
    "absent",
    "regular",
    "directory",
    "symlink",
    "fifo",
    "socket",
    "device",
    "other",
]


class WorkspaceBoundaryError(ValueError):
    """Raised when a path is outside the workspace or violates policy."""

    def __init__(self, message: str, *, code: str = "path_escapes_workspace") -> None:
        super().__init__(message)
        self.code = code


class PathFact(ContractModel):
    """Immutable snapshot of a workspace path at inspection time."""

    relative_path: str
    canonical_path: str
    exists: bool
    kind: FileKind
    device: int | None = None
    inode: int | None = None
    mode: int | None = None
    size: int | None = None
    mtime_ns: int | None = None
    content_hash: str | None = None
    unavailable_fields: tuple[str, ...] = ()

    def digest(self) -> str:
        payload = "|".join(
            [
                self.relative_path,
                self.canonical_path,
                str(self.exists).lower(),
                self.kind,
                _digest_field("device", self.device, self.unavailable_fields),
                _digest_field("inode", self.inode, self.unavailable_fields),
                _digest_field("mode", self.mode, self.unavailable_fields),
                _digest_field("size", self.size, self.unavailable_fields),
                _digest_field("mtime_ns", self.mtime_ns, self.unavailable_fields),
                self.content_hash or "",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest_field(name: str, value: int | None, unavailable: tuple[str, ...]) -> str:
    if name in unavailable or value is None:
        return f"{name}:unavailable"
    return f"{name}:{value}"


def kind_from_stat_mode(mode: int) -> FileKind:
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        return "device"
    return "other"


def _stat_field(stat_result: os.stat_result, name: str) -> tuple[int | None, bool]:
    value = getattr(stat_result, name, None)
    if value is None:
        return None, True
    return int(value), False


BUILT_IN_PROTECTED_NAMES = frozenset({".env", ".npmrc", ".pypirc", "credentials"})
BUILT_IN_PROTECTED_SUFFIXES = (".pem", ".key", ".p12")
SAFE_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})


class ProtectedPathPolicy:
    """Small, deterministic policy for files that may contain credentials."""

    def __init__(
        self,
        names: frozenset[str] = BUILT_IN_PROTECTED_NAMES,
        suffixes: tuple[str, ...] = BUILT_IN_PROTECTED_SUFFIXES,
    ) -> None:
        self.names = names
        self.suffixes = suffixes

    def is_protected(self, relative: Path) -> bool:
        name = relative.name
        if name in SAFE_ENV_TEMPLATES:
            return False
        return name in self.names or name.endswith(self.suffixes)


class WorkspacePaths:
    """Canonical path resolver for read and mutation operations."""

    def __init__(self, root: Path, protected: ProtectedPathPolicy | None = None) -> None:
        self.root = root.expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise WorkspaceBoundaryError(
                f"workspace is not a directory: {root}",
                code="workspace_not_a_directory",
            )
        self.protected = protected or ProtectedPathPolicy()

    @staticmethod
    def _relative(raw_path: str) -> Path:
        if not raw_path or not raw_path.strip():
            raise WorkspaceBoundaryError("path must not be empty", code="empty_path")
        normalized = raw_path.replace("\\", "/")
        relative = Path(normalized)
        if relative.is_absolute() or any(part == ".." for part in relative.parts):
            raise WorkspaceBoundaryError(
                f"path must be workspace-relative: {raw_path}",
                code="not_workspace_relative",
            )
        return relative

    def _within_root(self, candidate: Path) -> Path:
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceBoundaryError(
                "path escapes workspace",
                code="path_escapes_workspace",
            ) from exc
        return candidate

    def _content_hash(self, path: Path, kind: FileKind) -> str | None:
        if kind != "regular":
            return None
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()

    def _fact_from_lstat(
        self,
        relative: Path,
        physical: Path,
        *,
        follow_final: bool,
    ) -> PathFact:
        try:
            raw = os.lstat(physical)
        except FileNotFoundError:
            canonical = self._within_root((self.root / relative).resolve(strict=False))
            return PathFact(
                relative_path=relative.as_posix(),
                canonical_path=str(canonical),
                exists=False,
                kind="absent",
            )
        kind = kind_from_stat_mode(raw.st_mode)
        canonical = physical
        if follow_final:
            canonical = physical.resolve(strict=False)
            self._within_root(canonical)
        else:
            self._within_root((self.root / relative).resolve(strict=False))
            if kind == "symlink":
                raise WorkspaceBoundaryError(
                    f"symlink is not allowed for mutation: {relative.as_posix()}",
                    code="symlink_not_allowed",
                )
        unavailable: list[str] = []
        device, device_missing = _stat_field(raw, "st_dev")
        inode, inode_missing = _stat_field(raw, "st_ino")
        mode, mode_missing = _stat_field(raw, "st_mode")
        size, size_missing = _stat_field(raw, "st_size")
        mtime_ns, mtime_missing = _stat_field(raw, "st_mtime_ns")
        if device_missing:
            unavailable.append("device")
        if inode_missing:
            unavailable.append("inode")
        if mode_missing:
            unavailable.append("mode")
        if size_missing:
            unavailable.append("size")
        if mtime_missing:
            unavailable.append("mtime_ns")
        content_hash = None
        if kind == "regular" and not follow_final:
            content_hash = self._content_hash(physical, kind)
        elif kind == "regular" and follow_final:
            content_hash = self._content_hash(canonical, kind)
        elif kind == "symlink" and follow_final:
            target_kind = kind_from_stat_mode(os.stat(canonical).st_mode)
            if target_kind == "regular":
                content_hash = self._content_hash(canonical, "regular")
        return PathFact(
            relative_path=relative.as_posix(),
            canonical_path=str(canonical),
            exists=True,
            kind=kind,
            device=device,
            inode=inode,
            mode=None if mode is None else mode & 0o777,
            size=size,
            mtime_ns=mtime_ns,
            content_hash=content_hash,
            unavailable_fields=tuple(unavailable),
        )

    def inspect_read(self, raw_path: str) -> PathFact:
        relative = self._relative(raw_path)
        if self.protected.is_protected(relative):
            raise WorkspaceBoundaryError(f"protected path: {raw_path}", code="protected_path")
        physical = self.root / relative
        if physical.is_symlink():
            resolved = physical.resolve(strict=False)
            self._within_root(resolved)
        else:
            self._within_root(physical.resolve(strict=False))
        return self._fact_from_lstat(relative, physical, follow_final=True)

    def inspect_mutation(self, raw_path: str) -> PathFact:
        relative = self._relative(raw_path)
        if self.protected.is_protected(relative):
            raise WorkspaceBoundaryError(f"protected path: {raw_path}", code="protected_path")
        current = self.root
        for index, part in enumerate(relative.parts):
            current = current / part
            try:
                raw = os.lstat(current)
            except FileNotFoundError:
                if index < len(relative.parts) - 1:
                    continue
                canonical = self._within_root((self.root / relative).resolve(strict=False))
                return PathFact(
                    relative_path=relative.as_posix(),
                    canonical_path=str(canonical),
                    exists=False,
                    kind="absent",
                )
            if stat.S_ISLNK(raw.st_mode):
                raise WorkspaceBoundaryError(
                    f"symlink is not allowed for mutation: {raw_path}",
                    code="symlink_not_allowed",
                )
            if index < len(relative.parts) - 1:
                if not stat.S_ISDIR(raw.st_mode):
                    raise WorkspaceBoundaryError(
                        f"path is not a directory: {raw_path}",
                        code="not_a_directory",
                    )
                continue
            kind = kind_from_stat_mode(raw.st_mode)
            if kind != "regular":
                code = "not_regular_file" if kind == "directory" else "special_file"
                raise WorkspaceBoundaryError(
                    f"mutation target must be a regular file: {raw_path}",
                    code=code,
                )
        return self._fact_from_lstat(relative, self.root / relative, follow_final=False)

    def revalidate(self, fact: PathFact) -> PathFact:
        if not fact.exists or fact.kind == "absent":
            current = self.inspect_mutation(fact.relative_path)
            if current.exists or current.kind != "absent":
                raise WorkspaceBoundaryError(
                    f"path fact changed: {fact.relative_path}",
                    code="fact_mismatch",
                )
            return current
        identity_fields = ("device", "inode")
        missing = [name for name in identity_fields if name in fact.unavailable_fields]
        if missing or fact.device is None or fact.inode is None:
            raise WorkspaceBoundaryError(
                f"path fact identity is unavailable: {fact.relative_path}",
                code="fact_unavailable",
            )
        try:
            current = self.inspect_mutation(fact.relative_path)
        except WorkspaceBoundaryError as exc:
            if exc.code == "symlink_not_allowed":
                raise
            raise WorkspaceBoundaryError(
                f"path fact changed: {fact.relative_path}",
                code="fact_mismatch",
            ) from exc
        comparable = (
            current.relative_path == fact.relative_path
            and current.exists == fact.exists
            and current.kind == fact.kind
            and current.device == fact.device
            and current.inode == fact.inode
            and current.content_hash == fact.content_hash
        )
        if not comparable:
            raise WorkspaceBoundaryError(
                f"path fact changed: {fact.relative_path}",
                code="fact_mismatch",
            )
        return current

    def revalidate_fd(self, fact: PathFact, fd: int) -> None:
        if not fact.exists or fact.kind == "absent":
            raise WorkspaceBoundaryError(
                f"path fact changed: {fact.relative_path}",
                code="fact_mismatch",
            )
        if fact.device is None or fact.inode is None or fact.unavailable_fields:
            raise WorkspaceBoundaryError(
                f"path fact identity is unavailable: {fact.relative_path}",
                code="fact_unavailable",
            )
        current = os.fstat(fd)
        if current.st_dev != fact.device or current.st_ino != fact.inode:
            raise WorkspaceBoundaryError(
                f"path fact changed: {fact.relative_path}",
                code="fact_mismatch",
            )
        if not stat.S_ISREG(current.st_mode):
            raise WorkspaceBoundaryError(
                f"mutation target must be a regular file: {fact.relative_path}",
                code="not_regular_file",
            )

    def resolve_read(self, raw_path: str) -> Path:
        return Path(self.inspect_read(raw_path).canonical_path)

    def read_bytes(self, raw_path: str, limit: int | None = None) -> bytes:
        with self.resolve_read(raw_path).open("rb") as stream:
            return stream.read() if limit is None else stream.read(limit)

    def resolve_mutation(self, raw_path: str) -> Path:
        return Path(self.inspect_mutation(raw_path).canonical_path)

    def list_names(self, raw_path: str) -> list[str]:
        return [item.name for item in self.resolve_read(raw_path).iterdir()]

    def iter_files(self, raw_path: str, pattern: str = "*") -> Iterator[Path]:
        yield from self.resolve_read(raw_path).rglob(pattern)
