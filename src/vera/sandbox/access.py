"""Session-local file grants created only from an explicit approval decision."""

from __future__ import annotations

import os
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vera.workspace.paths import ProtectedPathPolicy

AccessMode = Literal["read", "read_write"]
AccessScope = Literal["once", "session"]
FileOperation = Literal["read", "write"]


class AccessDenied(ValueError):
    """No content may be read or operation started after this decision."""


@dataclass(frozen=True)
class ResourceIdentity:
    anchor: Path
    device: int
    inode: int
    is_directory: bool
    target: Path
    existed: bool

    @classmethod
    def capture(cls, path: Path) -> ResourceIdentity:
        anchor = path
        while not anchor.exists():
            if anchor == anchor.parent:
                raise AccessDenied("resource_unavailable")
            anchor = anchor.parent
        info = anchor.stat()
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise AccessDenied("special_file")
        return cls(
            anchor, info.st_dev, info.st_ino, stat.S_ISDIR(info.st_mode), path, anchor == path
        )

    def validate(self) -> None:
        try:
            info = os.lstat(self.anchor)
        except OSError as exc:
            raise AccessDenied("resource_changed") from exc
        if (info.st_dev, info.st_ino) != (self.device, self.inode) or stat.S_ISLNK(info.st_mode):
            raise AccessDenied("resource_changed")
        if self.anchor.resolve() != self.anchor:
            raise AccessDenied("resource_changed")
        if not self.existed and (self.target.exists() or self.target.is_symlink()):
            raise AccessDenied("resource_changed")


@dataclass(frozen=True)
class AccessRequest:
    request_id: str
    path: Path
    mode: AccessMode
    scope: AccessScope
    recursive: bool
    operation_id: str | None
    identity: ResourceIdentity


@dataclass(frozen=True)
class FileGrant:
    grant_id: str
    request: AccessRequest


@dataclass(frozen=True)
class FilePermissions:
    workspace: Path
    readable: tuple[Path, ...]
    writable: tuple[Path, ...]
    private_roots: tuple[Path, ...] = ()
    network: Literal["deny"] = "deny"
    revoked: threading.Event = field(default_factory=threading.Event, compare=False, repr=False)
    identities: tuple[ResourceIdentity, ...] = ()

    def __post_init__(self) -> None:
        if not self.identities:
            object.__setattr__(
                self,
                "identities",
                tuple(
                    ResourceIdentity.capture(path)
                    for path in dict.fromkeys((self.workspace, *self.readable, *self.writable))
                ),
            )

    def validate(self) -> None:
        if self.revoked.is_set():
            raise AccessDenied("permission_revoked")
        covered = {identity.target for identity in self.identities}
        if not set((self.workspace, *self.readable, *self.writable)).issubset(covered):
            raise AccessDenied("permission_identity_missing")
        for identity in self.identities:
            identity.validate()


class AccessSession:
    """An in-memory session, never reconstructed from project or recovery data.

    The trusted caller resolves a request only after the Core approval gate.
    Once grants bind an operation id and are consumed on entry, including failure.
    """

    def __init__(self, workspace: Path, *, private_roots: tuple[Path, ...] = ()) -> None:
        self.workspace = workspace.resolve(strict=True)
        if not self.workspace.is_dir():
            raise AccessDenied("workspace_not_directory")
        self._workspace_identity = ResourceIdentity.capture(self.workspace)
        self.private_roots = tuple(path.resolve() for path in private_roots)
        self._pending: dict[str, AccessRequest] = {}
        self._grants: dict[str, FileGrant] = {}
        self._lock = threading.RLock()
        self._closed = False
        self.generation = 0
        self._active: dict[str, tuple[set[str], threading.Event]] = {}

    def _check(self) -> None:
        if self._closed:
            raise AccessDenied("session_closed")
        self._workspace_identity.validate()

    def canonical(self, path: Path) -> Path:
        self._check()
        candidate = path if path.is_absolute() else self.workspace / path
        try:
            canonical = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            raise AccessDenied("invalid_path") from exc
        if any(canonical == root or root in canonical.parents for root in self.private_roots):
            raise AccessDenied("private_resource")
        return canonical

    def request(
        self,
        path: Path,
        mode: AccessMode,
        scope: AccessScope,
        *,
        operation_id: str | None = None,
    ) -> AccessRequest:
        with self._lock:
            if mode not in {"read", "read_write"} or scope not in {"once", "session"}:
                raise AccessDenied("invalid_permission")
            if scope == "once" and not operation_id:
                raise AccessDenied("operation_id_required")
            target = self.canonical(path)
            if ProtectedPathPolicy().is_protected(target):
                raise AccessDenied("protected_path")
            if target == Path(target.anchor):
                raise AccessDenied("filesystem_root_not_grantable")
            # A directory containing private state must not become a broad grant.
            if any(target == root or target in root.parents for root in self.private_roots):
                raise AccessDenied("private_resource")
            request = AccessRequest(
                uuid4().hex,
                target,
                mode,
                scope,
                target.is_dir(),
                operation_id,
                ResourceIdentity.capture(target),
            )
            self._pending[request.request_id] = request
            return request

    def resolve(self, request_id: str, *, approved: bool) -> FileGrant | None:
        with self._lock:
            self._check()
            request = self._pending.pop(request_id, None)
            if request is None:
                raise AccessDenied("unknown_or_resolved_request")
            if not approved:
                return None
            request.identity.validate()
            if self.canonical(request.path) != request.path:
                raise AccessDenied("resource_changed")
            grant = FileGrant(uuid4().hex, request)
            self._grants[grant.grant_id] = grant
            return grant

    @contextmanager
    def operation(
        self,
        operation_id: str,
        resources: tuple[tuple[Path, FileOperation], ...],
        *,
        consume: bool = True,
    ) -> Iterator[FilePermissions]:
        with self._lock:
            self._check()
            grants: dict[str, FileGrant] = {}
            for raw, mode in resources:
                if mode not in {"read", "write"}:
                    raise AccessDenied("invalid_operation")
                path = self.canonical(raw)
                if path == self.workspace or self.workspace in path.parents:
                    continue
                match = None
                for grant in self._grants.values():
                    request = grant.request
                    if request.scope == "once" and request.operation_id != operation_id:
                        continue
                    if mode == "write" and request.mode != "read_write":
                        continue
                    if path != request.path and not (
                        request.recursive and request.path in path.parents
                    ):
                        continue
                    request.identity.validate()
                    match = grant
                    break
                if match is None:
                    raise AccessDenied("file_access_approval_required")
                grants[match.grant_id] = match
            readable = [self.workspace]
            writable = [self.workspace]
            for grant in grants.values():
                readable.append(grant.request.path)
                if grant.request.mode == "read_write":
                    writable.append(grant.request.path)
                if consume and grant.request.scope == "once":
                    del self._grants[grant.grant_id]
            permission = FilePermissions(
                self.workspace,
                tuple(readable),
                tuple(writable),
                self.private_roots,
                identities=(
                    self._workspace_identity,
                    *(grant.request.identity for grant in grants.values()),
                ),
            )
            lease_id = uuid4().hex
            self._active[lease_id] = (set(grants), permission.revoked)
        try:
            yield permission
        finally:
            with self._lock:
                self._active.pop(lease_id, None)

    def revoke(self, grant_id: str) -> None:
        with self._lock:
            self._grants.pop(grant_id, None)
            for grants, cancelled in self._active.values():
                if grant_id in grants:
                    cancelled.set()

    def record_core_replacement(
        self, path: Path, previous: ResourceIdentity, created: ResourceIdentity
    ) -> None:
        """Advance only session grants for a file atomically replaced by trusted Core.

        created comes from the temporary file's descriptor, never from resolving
        an arbitrary replacement at the pathname after writing.
        """
        with self._lock:
            self._check()
            if created.target != path or created.is_directory:
                raise AccessDenied("resource_changed")
            for grant_id, grant in tuple(self._grants.items()):
                request = grant.request
                if (
                    request.scope == "session"
                    and request.path == path
                    and request.identity == previous
                ):
                    self._grants[grant_id] = replace(
                        grant, request=replace(request, identity=created)
                    )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self.reset()

    def reset(self) -> None:
        with self._lock:
            self.generation += 1
            self._pending.clear()
            self._grants.clear()
            for _, cancelled in self._active.values():
                cancelled.set()

    def command_resources(self, operation_id: str) -> tuple[tuple[Path, FileOperation], ...]:
        with self._lock:
            self._check()
            return tuple(
                (grant.request.path, "write" if grant.request.mode == "read_write" else "read")
                for grant in self._grants.values()
                if grant.request.scope == "session" or grant.request.operation_id == operation_id
            )

    def grants(self) -> tuple[FileGrant, ...]:
        with self._lock:
            self._check()
            return tuple(self._grants.values())
