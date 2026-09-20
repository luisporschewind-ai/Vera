"""Internal models used while discovering and validating Skill packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from vera.contracts.skills import SkillSourceKind, SkillSummary

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
