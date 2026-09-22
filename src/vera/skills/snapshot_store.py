"""Content-addressed, private and recoverable Skill snapshot storage."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vera.contracts.skills import SkillSnapshot
from vera.persistence.private_writer import PrivateAtomicWriter
from vera.skills.manifest import ManifestLoader
from vera.skills.models import (
    FrozenSkillFile,
    FrozenSkillSnapshot,
    ParsedSkillPackage,
    SnapshotCleanupReport,
    SnapshotReferenceReport,
)
from vera.skills.snapshot_codec import (
    SkillSnapshotCodec,
    SkillSnapshotCodecError,
    compute_snapshot_id,
)

_SNAPSHOT_ID = re.compile(r"^[0-9a-f]{64}$")
_RETENTION = timedelta(days=30)


class SkillSnapshotError(ValueError):
    def __init__(self, code: str, message: str = "Skill snapshot operation failed") -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class SkillSnapshotStore:
    def __init__(
        self,
        *,
        loader: ManifestLoader | None = None,
        codec: SkillSnapshotCodec | None = None,
    ) -> None:
        self.loader = loader or ManifestLoader()
        self.codec = codec or SkillSnapshotCodec()
        self.writer = PrivateAtomicWriter()

    def freeze(
        self,
        package: ParsedSkillPackage,
        *,
        state_dir: Path,
        created_at: datetime | None = None,
    ) -> FrozenSkillSnapshot:
        before = self._reload(package)
        frozen_files = tuple(
            FrozenSkillFile(
                relative_path=item.relative_path,
                kind=item.kind,
                content=item.content,
                content_hash=item.content_hash,
            )
            for item in before.files
        )
        snapshot_id = compute_snapshot_id(
            skill_id=before.skill_id,
            source_kind=before.source_kind,
            manifest=before.manifest,
            files=frozen_files,
        )
        snapshot = SkillSnapshot(
            snapshot_id=snapshot_id,
            skill_id=before.skill_id,
            name=before.manifest.name,
            version=before.manifest.version,
            source_kind=before.source_kind,
            manifest_hash=before.manifest_hash,
            package_hash=before.package_hash,
            resource_hash=before.resource_hash,
        )
        frozen = FrozenSkillSnapshot(
            snapshot=snapshot,
            manifest=before.manifest,
            files=frozen_files,
            created_at=(created_at or datetime.now(UTC)).astimezone(UTC),
        )
        payload = self.codec.encode(frozen)
        root = self._root(Path(state_dir))
        target = root / snapshot_id
        if target.exists() or target.is_symlink():
            try:
                return self.load(snapshot_id, state_dir=state_dir)
            except SkillSnapshotError as exc:
                raise SkillSnapshotError(
                    "skill_snapshot_corrupt", "existing snapshot is invalid"
                ) from exc

        temporary = Path(tempfile.mkdtemp(prefix=".tmp-", dir=root))
        try:
            self.writer.write_bytes(temporary / "snapshot.json", payload)
            self.writer.fsync_directory(temporary)
            after = self._reload(package)
            if not self._same_package(before, after):
                raise SkillSnapshotError(
                    "skill_source_changed", "Skill source changed during freeze"
                )
            try:
                os.rename(temporary, target)
            except FileExistsError:
                return self.load(snapshot_id, state_dir=state_dir)
            self.writer.fsync_directory(root)
            temporary = Path()
            return frozen
        except SkillSnapshotError:
            raise
        except OSError as exc:
            raise SkillSnapshotError("skill_snapshot_write_failed", str(exc)) from exc
        finally:
            if temporary != Path():
                shutil.rmtree(temporary, ignore_errors=True)

    def load(self, snapshot_id: str, *, state_dir: Path) -> FrozenSkillSnapshot:
        if _SNAPSHOT_ID.fullmatch(snapshot_id) is None:
            raise SkillSnapshotError("skill_snapshot_missing", "invalid snapshot id")
        root = self._root(Path(state_dir), create=False)
        target = root / snapshot_id
        try:
            info = os.lstat(target)
            metadata = os.lstat(target / "snapshot.json")
        except FileNotFoundError as exc:
            raise SkillSnapshotError("skill_snapshot_missing") from exc
        except OSError as exc:
            raise SkillSnapshotError("skill_snapshot_corrupt") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SkillSnapshotError(
                "skill_snapshot_corrupt", "snapshot root is not a private directory"
            )
        if (
            stat.S_IMODE(info.st_mode) != 0o700
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
        ):
            raise SkillSnapshotError(
                "skill_snapshot_corrupt", "snapshot permissions or file type are invalid"
            )
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise SkillSnapshotError(
                "skill_snapshot_corrupt", "snapshot file permissions are invalid"
            )
        try:
            return self.codec.decode((target / "snapshot.json").read_bytes())
        except SkillSnapshotCodecError as exc:
            raise SkillSnapshotError(exc.code, str(exc)) from exc

    def scan_references(
        self,
        *,
        runs: Iterable[object],
        sessions: Iterable[object],
    ) -> SnapshotReferenceReport:
        found: set[str] = set()
        uncertain = False
        for record in (*runs, *sessions):
            value = self._record_snapshot_id(record)
            if value is None:
                uncertain = True
            elif _SNAPSHOT_ID.fullmatch(value):
                found.add(value)
            else:
                uncertain = True
        return SnapshotReferenceReport(referenced_ids=tuple(sorted(found)), uncertain=uncertain)

    def collect(
        self,
        *,
        now: datetime,
        references: SnapshotReferenceReport,
        state_dir: Path | None = None,
    ) -> SnapshotCleanupReport:
        try:
            root = self._root(Path(state_dir or "."), create=False)
        except SkillSnapshotError:
            return SnapshotCleanupReport(reason_code="skill_snapshot_cleanup_refused")
        if not root.exists():
            return SnapshotCleanupReport()
        children = tuple(sorted(root.iterdir(), key=lambda item: item.name))
        scanned: list[str] = []
        retained: list[str] = []
        deleted: list[str] = []
        refused: list[str] = []
        reason_code: str | None = None
        for child in children:
            if _SNAPSHOT_ID.fullmatch(child.name) is None:
                continue
            scanned.append(child.name)
            if references.uncertain or child.name in references.referenced_ids:
                if references.uncertain:
                    refused.append(child.name)
                    reason_code = "skill_snapshot_cleanup_refused"
                else:
                    retained.append(child.name)
                continue
            try:
                frozen = self.load(child.name, state_dir=state_dir or Path("."))
            except SkillSnapshotError:
                refused.append(child.name)
                reason_code = "skill_snapshot_cleanup_refused"
                continue
            if now.astimezone(UTC) - frozen.created_at < _RETENTION:
                retained.append(child.name)
                continue
            if child.is_symlink() or not child.is_dir():
                refused.append(child.name)
                reason_code = "skill_snapshot_cleanup_refused"
                continue
            shutil.rmtree(child)
            deleted.append(child.name)
        return SnapshotCleanupReport(
            scanned_ids=tuple(scanned),
            retained_ids=tuple(retained),
            deleted_ids=tuple(deleted),
            refused_ids=tuple(refused),
            reason_code=reason_code,
        )

    def _reload(self, package: ParsedSkillPackage) -> ParsedSkillPackage:
        try:
            current = self.loader.load(package.package_root, source_kind=package.source_kind)
        except Exception as exc:
            raise SkillSnapshotError(
                "skill_source_changed", "Skill source is no longer stable"
            ) from exc
        if not self._same_package(package, current):
            raise SkillSnapshotError("skill_source_changed", "Skill source changed before freeze")
        return current

    @staticmethod
    def _same_package(left: ParsedSkillPackage, right: ParsedSkillPackage) -> bool:
        return (
            left.skill_id == right.skill_id
            and left.manifest_hash == right.manifest_hash
            and left.resource_hash == right.resource_hash
            and left.package_hash == right.package_hash
        )

    def _root(self, state_dir: Path, *, create: bool = True) -> Path:
        root = state_dir / "skills" / "snapshots" / "sha256"
        try:
            info = os.lstat(root)
        except FileNotFoundError:
            info = None
        except OSError as exc:
            raise SkillSnapshotError(
                "skill_snapshot_write_failed" if create else "skill_snapshot_cleanup_refused"
            ) from exc
        if info is not None and (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)):
            raise SkillSnapshotError(
                "skill_snapshot_write_failed" if create else "skill_snapshot_cleanup_refused"
            )
        if create:
            try:
                self.writer.ensure_directory(root)
            except Exception as exc:
                raise SkillSnapshotError("skill_snapshot_write_failed") from exc
        return root

    @staticmethod
    def _record_snapshot_id(record: object) -> str | None:
        value: object
        if isinstance(record, Mapping):
            value = record.get("snapshot_id")
            if value is None and isinstance(record.get("skill_snapshot"), Mapping):
                value = record["skill_snapshot"].get("snapshot_id")
        else:
            value = getattr(record, "snapshot_id", None)
            if value is None:
                nested = getattr(record, "skill_snapshot", None)
                value = getattr(nested, "snapshot_id", None)
        return value if isinstance(value, str) else None
