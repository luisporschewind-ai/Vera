"""Atomic ChangeSet application and conflict-safe rollback."""

import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from vera.contracts.checkpoints import CheckpointManifest
from vera.contracts.recovery import RecoveryPlan
from vera.workspace.changeset import ABSENT_HASH, BuiltChangeSet, sha256_bytes
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


class ApplyStatus(StrEnum):
    APPLIED = "applied"
    REJECTED = "rejected"
    RESTORED_AFTER_FAILURE = "restored_after_failure"
    RECOVERY_REQUIRED = "recovery_required"


class RollbackStatus(StrEnum):
    ROLLED_BACK = "rolled_back"
    CONFLICTED = "conflicted"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True)
class ApplyResult:
    status: ApplyStatus
    paths: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class RollbackResult:
    status: RollbackStatus
    paths: tuple[str, ...] = ()
    error: str | None = None


class SimulatedCrash(RuntimeError):
    """Injected crash used by recovery tests to abandon the process mid-effect."""


class FileWriter(Protocol):
    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None: ...

    def delete(self, path: Path) -> None: ...


class AtomicFileWriter:
    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            existing = os.open(path, flags)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            os.close(existing)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return
        os.close(fd)
        path.unlink(missing_ok=True)


class ChangeApplier:
    def __init__(
        self,
        paths: WorkspacePaths,
        checkpoint_store: CheckpointStore,
        writer: FileWriter | None = None,
    ) -> None:
        self.paths = paths
        self.checkpoint_store = checkpoint_store
        self.writer = writer or AtomicFileWriter()

    def _preflight(self, built: BuiltChangeSet, manifest: CheckpointManifest) -> tuple[str, ...]:
        changes = built.change_set.files
        expected_paths = {item.path for item in changes}
        if manifest.run_id != built.change_set.run_id or set(manifest.before) != expected_paths:
            raise ValueError("checkpoint does not match changeset")
        for change in changes:
            fact = built.path_facts.get(change.path)
            if fact is None:
                raise ValueError(f"missing path fact: {change.path}")
            self.paths.revalidate(fact)
            target = self.paths.resolve_mutation(change.path)
            current_exists = target.exists()
            record = manifest.before[change.path]
            if current_exists != record.existed:
                raise ValueError(f"before existence changed: {change.path}")
            if current_exists:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(target, flags)
                try:
                    self.paths.revalidate_fd(fact, fd)
                    if sha256_bytes(target.read_bytes()) != record.content_hash:
                        raise ValueError(f"before hash changed: {change.path}")
                finally:
                    os.close(fd)
            if change.operation != "delete" and change.path not in built.intended_bytes:
                raise ValueError(f"missing intended bytes: {change.path}")
        return tuple(item.path for item in changes)

    def _restore(self, manifest: CheckpointManifest, paths: tuple[str, ...]) -> None:
        for relative in paths:
            target = self.paths.resolve_mutation(relative)
            record = manifest.before[relative]
            if record.existed:
                self.writer.replace(
                    target,
                    self.checkpoint_store.read_original(manifest, relative),
                    record.mode,
                )
            else:
                self.writer.delete(target)

    def apply(self, built: BuiltChangeSet, manifest: CheckpointManifest) -> ApplyResult:
        try:
            paths = self._preflight(built, manifest)
        except (OSError, ValueError) as exc:
            return ApplyResult(ApplyStatus.REJECTED, error=str(exc))
        try:
            for change in built.change_set.files:
                target = self.paths.resolve_mutation(change.path)
                if change.operation == "delete":
                    self.writer.delete(target)
                else:
                    self.writer.replace(target, built.intended_bytes[change.path])
        except SimulatedCrash:
            raise
        except Exception as exc:
            try:
                self._restore(manifest, paths)
            except Exception as recovery_error:
                return ApplyResult(
                    ApplyStatus.RECOVERY_REQUIRED,
                    paths=paths,
                    error=f"{exc}; recovery failed: {recovery_error}",
                )
            return ApplyResult(ApplyStatus.RESTORED_AFTER_FAILURE, paths=paths, error=str(exc))
        return ApplyResult(ApplyStatus.APPLIED, paths=paths)

    def rollback(self, manifest: CheckpointManifest) -> RollbackResult:
        paths = tuple(manifest.before)
        try:
            for relative in paths:
                target = self.paths.resolve_mutation(relative)
                current_hash = (
                    ABSENT_HASH if not target.exists() else sha256_bytes(target.read_bytes())
                )
                if current_hash != manifest.after_hashes[relative]:
                    return RollbackResult(RollbackStatus.CONFLICTED, paths=paths)
            self._restore(manifest, paths)
        except Exception as exc:
            return RollbackResult(RollbackStatus.RECOVERY_REQUIRED, paths=paths, error=str(exc))
        return RollbackResult(RollbackStatus.ROLLED_BACK, paths=paths)

    def restore_partial(self, plan: RecoveryPlan, manifest: CheckpointManifest) -> RollbackResult:
        try:
            restore_paths = self._preflight_partial(plan, manifest)
        except (OSError, ValueError) as exc:
            return RollbackResult(RollbackStatus.RECOVERY_REQUIRED, error=str(exc))
        try:
            self._restore(manifest, restore_paths)
        except Exception as exc:
            return RollbackResult(
                RollbackStatus.RECOVERY_REQUIRED,
                paths=restore_paths,
                error=str(exc),
            )
        return RollbackResult(RollbackStatus.ROLLED_BACK, paths=restore_paths)

    def _preflight_partial(
        self, plan: RecoveryPlan, manifest: CheckpointManifest
    ) -> tuple[str, ...]:
        restore_paths: list[str] = []
        for item in plan.files:
            if item.path not in manifest.before:
                raise ValueError(f"checkpoint missing path: {item.path}")
            target = self.paths.resolve_mutation(item.path)
            current_hash = ABSENT_HASH if not target.exists() else sha256_bytes(target.read_bytes())
            if current_hash != item.current_hash:
                raise ValueError(f"current hash changed: {item.path}")
            if item.action == "keep_before" and current_hash != item.before_hash:
                raise ValueError(f"keep_before mismatch: {item.path}")
            if item.action == "restore_before" and current_hash != item.after_hash:
                raise ValueError(f"restore_before mismatch: {item.path}")
            if item.action == "restore_before":
                record = manifest.before[item.path]
                if record.existed:
                    self.checkpoint_store.read_original(manifest, item.path)
                restore_paths.append(item.path)
        return tuple(restore_paths)
