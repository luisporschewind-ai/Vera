"""Stable public summaries and explicit selector resolution."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.skills import SkillSelection, SkillSummary
from vera.skills.discovery import SkillDiscovery
from vera.skills.manifest import summary_for_package
from vera.skills.models import SkillCandidate


class SkillRegistry:
    def __init__(self, discovery: SkillDiscovery) -> None:
        self.discovery = discovery

    def candidates(self, workspace_root: Path) -> tuple[SkillCandidate, ...]:
        return self.discovery.discover(workspace_root)

    def summaries(self, workspace_root: Path) -> tuple[SkillSummary, ...]:
        candidates = list(self.candidates(workspace_root))
        available_by_name: dict[str, list[SkillCandidate]] = {}
        for candidate in candidates:
            if candidate.package is not None and candidate.summary.availability == "available":
                available_by_name.setdefault(candidate.package.manifest.name, []).append(candidate)
        summaries: list[SkillSummary] = []
        for candidate in candidates:
            summary = candidate.summary
            if (
                candidate.package is not None
                and len(available_by_name[candidate.package.manifest.name]) > 1
            ):
                summary = summary_for_package(
                    candidate.package,
                    availability="conflict",
                    reason_codes=("skill_name_conflict",),
                )
            summaries.append(summary)
        return tuple(
            sorted(
                summaries, key=lambda item: (item.name or "", item.source_kind, item.skill_id or "")
            )
        )

    def resolve(self, selector: str, workspace_root: Path) -> SkillSelection:
        summaries = self.summaries(workspace_root)
        exact = [item for item in summaries if item.skill_id == selector]
        if ":" in selector:
            if not exact:
                return SkillSelection(
                    mode="explicit",
                    selector=selector,
                    status="invalid",
                    reason_codes=("skill_not_found",),
                )
            return self._selection_from_summary(exact[0], selector, allow_conflict=True)
        named = [item for item in summaries if item.name == selector]
        if len(named) != 1:
            reason = "skill_not_found" if not named else "skill_name_conflict"
            return SkillSelection(
                mode="explicit", selector=selector, status="invalid", reason_codes=(reason,)
            )
        return self._selection_from_summary(named[0], selector)

    @staticmethod
    def _selection_from_summary(
        summary: SkillSummary, selector: str, *, allow_conflict: bool = False
    ) -> SkillSelection:
        if summary.availability != "available" and not (
            allow_conflict and summary.availability == "conflict"
        ):
            return SkillSelection(
                mode="explicit",
                selector=selector,
                status="invalid",
                skill_id=summary.skill_id,
                source_kind=summary.source_kind,
                version=summary.version,
                manifest_hash=summary.manifest_hash,
                reason_codes=summary.reason_codes,
            )
        return SkillSelection(
            mode="explicit",
            selector=selector,
            status="selected",
            skill_id=summary.skill_id,
            source_kind=summary.source_kind,
            version=summary.version,
            manifest_hash=summary.manifest_hash,
        )
