"""Internal models used while discovering and validating Skill packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from vera.contracts.skills import SkillSnapshot, SkillSourceKind, SkillSummary

if TYPE_CHECKING:
    from vera.skills.manifest import SkillManifest

SkillFileKind = Literal["entry", "reference", "template"]


@dataclass(frozen=True)
class SkillFile:
    relative_path: str
    kind: SkillFileKind
    content: bytes
    content_hash: str


@dataclass(frozen=True)
class ParsedSkillPackage:
    package_root: Path
    source_kind: SkillSourceKind
    skill_id: str
    manifest: SkillManifest
    manifest_hash: str
    files: tuple[SkillFile, ...]
    resource_hash: str
    package_hash: str

    def public_facts_json(self) -> str:
        return json.dumps(
            {
                "skill_id": self.skill_id,
                "source_kind": self.source_kind,
                "manifest_hash": self.manifest_hash,
                "resource_hash": self.resource_hash,
                "files": [
                    {
                        "path": item.relative_path,
                        "kind": item.kind,
                        "byte_count": len(item.content),
                        "content_hash": item.content_hash,
                    }
                    for item in self.files
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )


@dataclass(frozen=True)
class SkillCandidate:
    package_root: Path
    source_kind: SkillSourceKind
    summary: SkillSummary
    package: ParsedSkillPackage | None = None


@dataclass(frozen=True)
class FrozenSkillFile:
    relative_path: str
    kind: SkillFileKind
    content: bytes
    content_hash: str


@dataclass(frozen=True)
class FrozenSkillSnapshot:
    snapshot: SkillSnapshot
    manifest: SkillManifest
    files: tuple[FrozenSkillFile, ...]
    created_at: datetime

    @property
    def snapshot_id(self) -> str:
        return self.snapshot.snapshot_id

    def context_files(self) -> tuple[FrozenSkillFile, ...]:
        return self.files


@dataclass(frozen=True)
class SnapshotReferenceReport:
    referenced_ids: tuple[str, ...] = ()
    uncertain: bool = False


@dataclass(frozen=True)
class SnapshotCleanupReport:
    scanned_ids: tuple[str, ...] = ()
    retained_ids: tuple[str, ...] = ()
    deleted_ids: tuple[str, ...] = ()
    refused_ids: tuple[str, ...] = ()
    reason_code: str | None = None
