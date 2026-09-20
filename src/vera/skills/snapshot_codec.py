"""Private codec for immutable Core-native Skill snapshots."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from vera.contracts.skills import SkillSnapshot
from vera.skills.manifest import MAX_FILES, MAX_PACKAGE_BYTES, SkillManifest
from vera.skills.models import FrozenSkillFile, FrozenSkillSnapshot

SNAPSHOT_FORMAT_VERSION = 1


class SkillSnapshotCodecError(ValueError):
    def __init__(self, code: str, message: str = "invalid Skill snapshot") -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _hash_files(files: tuple[FrozenSkillFile, ...]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(item.content).to_bytes(8, "big"))
        digest.update(item.content)
    return digest.hexdigest()


def compute_snapshot_id(
    *, skill_id: str, source_kind: str, manifest: SkillManifest, files: tuple[FrozenSkillFile, ...]
) -> str:
    digest = hashlib.sha256()
    digest.update(b"vera.skill.snapshot.v1\0")
    digest.update(_canonical({"skill_id": skill_id, "source_kind": source_kind}))
    digest.update(b"\0")
    digest.update(_canonical(manifest.model_dump(mode="json")))
    for item in sorted(files, key=lambda file: file.relative_path):
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(item.content).to_bytes(8, "big"))
        digest.update(item.content)
    return digest.hexdigest()


def _decode_b64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise SkillSnapshotCodecError("skill_snapshot_corrupt", "file content is not base64")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise SkillSnapshotCodecError("skill_snapshot_corrupt", "file content is invalid") from exc


class SkillSnapshotCodec:
    def encode(self, frozen: FrozenSkillSnapshot) -> bytes:
        payload = {
            "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
            "snapshot": frozen.snapshot.model_dump(mode="json"),
            "manifest": frozen.manifest.model_dump(mode="json"),
            "files": [
                {
                    "path": item.relative_path,
                    "kind": item.kind,
                    "byte_count": len(item.content),
                    "content_hash": item.content_hash,
                    "content_b64": base64.b64encode(item.content).decode("ascii"),
                }
                for item in frozen.files
            ],
            "created_at": frozen.created_at.astimezone(UTC).isoformat(),
        }
        return _canonical(payload)

    def decode(self, data: bytes | str) -> FrozenSkillSnapshot:
        try:
            raw = data.decode("utf-8") if isinstance(data, bytes) else data
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillSnapshotCodecError(
                "skill_snapshot_corrupt", "snapshot JSON is invalid"
            ) from exc
        if not isinstance(payload, dict):
            raise SkillSnapshotCodecError("skill_snapshot_corrupt", "snapshot object is required")
        if payload.get("snapshot_format_version") != SNAPSHOT_FORMAT_VERSION:
            raise SkillSnapshotCodecError("skill_snapshot_version_unsupported")
        if set(payload) != {
            "snapshot_format_version",
            "snapshot",
            "manifest",
            "files",
            "created_at",
        }:
            raise SkillSnapshotCodecError("skill_snapshot_corrupt", "snapshot fields are invalid")
        try:
            snapshot = SkillSnapshot.model_validate(payload["snapshot"])
            manifest = SkillManifest.model_validate(payload["manifest"])
            raw_files = payload["files"]
            if not isinstance(raw_files, list) or not raw_files or len(raw_files) > MAX_FILES:
                raise SkillSnapshotCodecError(
                    "skill_snapshot_corrupt", "snapshot files are invalid"
                )
            files: list[FrozenSkillFile] = []
            seen: set[str] = set()
            for raw_file in raw_files:
                if not isinstance(raw_file, dict) or set(raw_file) != {
                    "path",
                    "kind",
                    "byte_count",
                    "content_hash",
                    "content_b64",
                }:
                    raise SkillSnapshotCodecError(
                        "skill_snapshot_corrupt", "snapshot file is invalid"
                    )
                content = _decode_b64(raw_file["content_b64"])
                path = raw_file["path"]
                kind = raw_file["kind"]
                if not isinstance(path, str) or path in seen or not isinstance(kind, str):
                    raise SkillSnapshotCodecError(
                        "skill_snapshot_corrupt", "snapshot path is invalid"
                    )
                path_parts = PurePosixPath(path).parts
                valid_entry = path == "SKILL.md" and kind == "entry"
                valid_resource = (
                    len(path_parts) >= 2
                    and path_parts[0] in {"references", "templates"}
                    and kind in {"reference", "template"}
                    and all(part not in {"", ".", ".."} for part in path_parts)
                    and "\\" not in path
                )
                if not (valid_entry or valid_resource):
                    raise SkillSnapshotCodecError(
                        "skill_snapshot_corrupt", "snapshot path is invalid"
                    )
                if raw_file["byte_count"] != len(content) or len(content) > 64 * 1024:
                    raise SkillSnapshotCodecError(
                        "skill_snapshot_corrupt", "snapshot size is invalid"
                    )
                if hashlib.sha256(content).hexdigest() != raw_file["content_hash"]:
                    raise SkillSnapshotCodecError(
                        "skill_snapshot_corrupt", "snapshot file hash mismatch"
                    )
                content.decode("utf-8")
                seen.add(path)
                files.append(
                    FrozenSkillFile(
                        relative_path=path,
                        kind=kind,  # type: ignore[arg-type]
                        content=content,
                        content_hash=raw_file["content_hash"],
                    )
                )
            normalized_files = tuple(sorted(files, key=lambda file: file.relative_path))
            if (
                sum(len(item.content) for item in normalized_files)
                + len(_canonical(payload["manifest"]))
                > MAX_PACKAGE_BYTES
            ):
                raise SkillSnapshotCodecError("skill_snapshot_corrupt", "snapshot is too large")
            if snapshot.resource_hash != _hash_files(normalized_files):
                raise SkillSnapshotCodecError("skill_snapshot_corrupt", "resource hash mismatch")
            if normalized_files[0].relative_path != "SKILL.md":
                raise SkillSnapshotCodecError("skill_snapshot_corrupt", "entry file is missing")
            if snapshot.snapshot_id != compute_snapshot_id(
                skill_id=snapshot.skill_id,
                source_kind=snapshot.source_kind,
                manifest=manifest,
                files=normalized_files,
            ):
                raise SkillSnapshotCodecError("skill_snapshot_corrupt", "snapshot id mismatch")
            created_at = datetime.fromisoformat(payload["created_at"])
            if created_at.tzinfo is None:
                raise ValueError("created_at must be timezone aware")
        except SkillSnapshotCodecError:
            raise
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            raise SkillSnapshotCodecError(
                "skill_snapshot_corrupt", "snapshot facts are invalid"
            ) from exc
        return FrozenSkillSnapshot(
            snapshot=snapshot,
            manifest=manifest,
            files=normalized_files,
            created_at=created_at.astimezone(UTC),
        )
