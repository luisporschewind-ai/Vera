"""Session-scoped explicit Skill selection."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.skills import SkillSelection
from vera.skills.models import SkillCandidate
from vera.skills.registry import SkillRegistry


class SkillSelectionService:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry
        self._pending = SkillSelection()

    @property
    def pending(self) -> SkillSelection:
        return self._pending

    def select(self, selector: str, workspace_root: Path) -> SkillSelection:
        self._pending = self.registry.resolve(selector, workspace_root)
        return self._pending

    def clear(self) -> SkillSelection:
        self._pending = SkillSelection()
        return self._pending

    def restore(self, selection: SkillSelection) -> None:
        self._pending = selection

    def consume_for_run(self, workspace_root: Path) -> SkillSelection:
        selection = self._pending
        if selection.status == "selected":
            candidate = self.registry.package_for(selection, workspace_root)
            if candidate is None or candidate.package is None:
                return selection.model_copy(
                    update={
                        "status": "invalid",
                        "reason_codes": ("skill_source_changed",),
                    }
                )
            self._pending = SkillSelection()
        return selection

    def package_for(self, selection: SkillSelection, workspace_root: Path) -> SkillCandidate | None:
        return self.registry.package_for(selection, workspace_root)
