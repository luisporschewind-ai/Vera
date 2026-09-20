"""Safe discovery of local Skill package roots."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from vera.config import user_skills_path
from vera.contracts.skills import SkillSourceKind, SkillSummary, SkillTrustLevel
from vera.skills.manifest import (
    ManifestLoader,
    SkillValidationError,
    summary_for_error,
    summary_for_package,
)
from vera.skills.models import SkillCandidate


def _trust(source_kind: SkillSourceKind) -> SkillTrustLevel:
    return "untrusted" if source_kind == "workspace" else "advisory"


class SkillDiscovery:
    def __init__(
        self,
        *,
        builtin_root: Path | None = None,
        user_root: Path | None = None,
        loader: ManifestLoader | None = None,
    ) -> None:
        self.builtin_root = builtin_root or Path(__file__).resolve().parent / "builtin_skills"
        self.user_root = user_root or user_skills_path()
        self.loader = loader or ManifestLoader()

    def discover(self, workspace_root: Path) -> tuple[SkillCandidate, ...]:
        roots: tuple[tuple[SkillSourceKind, Path], ...] = (
            ("builtin", self.builtin_root),
            ("user", self.user_root),
            ("workspace", Path(workspace_root) / ".vera" / "skills"),
        )
        candidates: list[SkillCandidate] = []
        for source_kind, root in roots:
            candidates.extend(self._discover_root(source_kind, root))
        return tuple(candidates)

    def _discover_root(self, source_kind: SkillSourceKind, root: Path) -> list[SkillCandidate]:
        try:
            root_info = os.lstat(root)
        except FileNotFoundError:
            return []
        except OSError:
            return []
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            return []
        try:
            children = sorted(root.iterdir(), key=lambda item: item.name)
        except OSError:
            return []
        candidates: list[SkillCandidate] = []
        for child in children:
            try:
                info = os.lstat(child)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode):
                summary = SkillSummary(
                    source_kind=source_kind,
                    trust_level=_trust(source_kind),
                    availability="invalid",
                    reason_codes=("skill_symlink_refused",),
                )
                candidates.append(SkillCandidate(child, source_kind, summary))
                continue
            if not stat.S_ISDIR(info.st_mode):
                continue
            try:
                package = self.loader.load(child, source_kind=source_kind)
            except SkillValidationError as exc:
                candidates.append(
                    SkillCandidate(child, source_kind, summary_for_error(source_kind, exc))
                )
            else:
                candidates.append(
                    SkillCandidate(child, source_kind, summary_for_package(package), package)
                )
        return candidates
