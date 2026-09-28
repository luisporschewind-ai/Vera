"""Private, atomic persistence for durable workspace permission grants."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from pydantic import ValidationError

from vera.contracts.errors import classify_os_error
from vera.persistence.errors import PersistenceFault
from vera.persistence.private_writer import PrivateAtomicWriter
from vera.policy.permissions import WorkspacePermissionSnapshot


class WorkspacePermissionStoreError(PersistenceFault):
    """A private permission record could not be trusted or persisted."""


class WorkspacePermissionStore:
    def __init__(
        self,
        state_dir: Path,
        *,
        policy_major_version: int,
        protected_roots_hash: str,
        replace: Callable[[Path, Path], None] = os.replace,
        fsync: Callable[[int], None] = os.fsync,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.policy_major_version = policy_major_version
        self.protected_roots_hash = protected_roots_hash
        self._replace = replace
        self._fsync = fsync
        self._directory_writer = PrivateAtomicWriter()

    def path_for(self, workspace_identity: str) -> Path:
        digest = hashlib.sha256(workspace_identity.encode("utf-8")).hexdigest()
        return self.state_dir / "permissions" / f"{digest}.json"

    def load(self, workspace_identity: str) -> WorkspacePermissionSnapshot:
        target = self.path_for(workspace_identity)
        if not target.exists():
            return self._empty(workspace_identity)
        self._assert_private_directory(target.parent)
        self._assert_private_file(target)
        try:
            raw = target.read_bytes()
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._quarantine(target, raw if "raw" in locals() else b"", "corrupt")
            raise WorkspacePermissionStoreError("mid_file_corrupt") from exc
        except OSError as exc:
            raise WorkspacePermissionStoreError(classify_os_error(exc)) from exc
        if not isinstance(payload, dict):
            self._quarantine(target, raw, "corrupt")
            raise WorkspacePermissionStoreError("invalid_permission_snapshot")
        version = payload.get("schema_version")
        if version != 1:
            if isinstance(version, int) and version > 1:
                raise WorkspacePermissionStoreError("unsupported_version", version=version)
            self._quarantine(target, raw, "corrupt")
            raise WorkspacePermissionStoreError("invalid_permission_snapshot")
        try:
            snapshot = WorkspacePermissionSnapshot.model_validate(payload)
        except ValidationError as exc:
            self._quarantine(target, raw, "corrupt")
            raise WorkspacePermissionStoreError("invalid_permission_snapshot", version=1) from exc
        if (
            snapshot.workspace_identity != workspace_identity
            or snapshot.policy_major_version != self.policy_major_version
            or snapshot.protected_roots_hash != self.protected_roots_hash
        ):
            self._quarantine(target, raw, "stale")
            return self._empty(workspace_identity)
        return snapshot

    def save(self, snapshot: WorkspacePermissionSnapshot) -> None:
        if snapshot.policy_major_version != self.policy_major_version:
            raise WorkspacePermissionStoreError("policy_version_mismatch")
        if snapshot.protected_roots_hash != self.protected_roots_hash:
            raise WorkspacePermissionStoreError("protected_roots_mismatch")
        if any(grant.scope != "workspace" for grant in snapshot.grants):
            raise WorkspacePermissionStoreError("transient_grant_persistence_forbidden")
        target = self.path_for(snapshot.workspace_identity)
        directory = target.parent
        payload = json.dumps(
            snapshot.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        temporary: Path | None = None
        descriptor = -1
        try:
            self._ensure_private_directory(directory)
            if target.exists():
                self._assert_private_file(target)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=directory
            )
            temporary = Path(temporary_name)
            os.fchmod(descriptor, 0o600)
            _write_all(descriptor, payload)
            self._fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            self._replace(temporary, target)
            temporary = None
            self._fsync_directory(directory)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            mapped = classify_os_error(exc)
            code = "permission_write_failed" if mapped == "write_failed" else mapped
            raise WorkspacePermissionStoreError(code) from exc
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def revoke(self, workspace_identity: str) -> None:
        target = self.path_for(workspace_identity)
        if not target.exists():
            return
        self._assert_private_file(target)
        try:
            target.unlink()
            self._fsync_directory(target.parent)
        except OSError as exc:
            raise WorkspacePermissionStoreError(classify_os_error(exc)) from exc

    def _empty(self, workspace_identity: str) -> WorkspacePermissionSnapshot:
        return WorkspacePermissionSnapshot(
            workspace_identity=workspace_identity,
            policy_major_version=self.policy_major_version,
            trusted=False,
            protected_roots_hash=self.protected_roots_hash,
            grants=(),
        )

    def _ensure_private_directory(self, directory: Path) -> None:
        try:
            self._directory_writer.ensure_directory(directory)
        except OSError as exc:
            raise WorkspacePermissionStoreError(classify_os_error(exc)) from exc
        self._assert_private_directory(directory)

    def _assert_private_directory(self, directory: Path) -> None:
        try:
            details = directory.lstat()
        except OSError as exc:
            raise WorkspacePermissionStoreError(classify_os_error(exc)) from exc
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o700
        ):
            raise WorkspacePermissionStoreError("invalid_private_directory")

    def _assert_private_file(self, target: Path) -> None:
        try:
            details = target.lstat()
        except OSError as exc:
            raise WorkspacePermissionStoreError(classify_os_error(exc)) from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
        ):
            raise WorkspacePermissionStoreError("invalid_permission_path")

    def _quarantine(self, target: Path, raw: bytes, kind: str) -> None:
        suffix = hashlib.sha256(raw).hexdigest()[:12]
        quarantine = target.with_name(f"{target.name}.{kind}-{suffix}")
        counter = 1
        while quarantine.exists():
            quarantine = target.with_name(f"{target.name}.{kind}-{suffix}-{counter}")
            counter += 1
        try:
            self._replace(target, quarantine)
            self._fsync_directory(target.parent)
        except OSError as exc:
            self._raise_quarantine_failure(exc)

    def _fsync_directory(self, directory: Path) -> None:
        descriptor = -1
        try:
            descriptor = os.open(directory, os.O_RDONLY)
            self._fsync(descriptor)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _raise_quarantine_failure(exc: OSError) -> NoReturn:
        raise WorkspacePermissionStoreError("permission_quarantine_failed") from exc


def _write_all(descriptor: int, data: bytes) -> None:
    written = 0
    view = memoryview(data)
    while written < len(data):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("short permission write")
        written += count
