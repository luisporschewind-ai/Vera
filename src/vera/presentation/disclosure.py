"""Disclosure rules for timeline blocks."""

from __future__ import annotations

from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock


class DisclosurePolicy:
    """Pure functions deciding default and failure-driven expansion."""

    def initial_state(self, kind: BlockKind, status: BlockStatus) -> bool:
        if status is BlockStatus.FAILED:
            return True
        match kind:
            case BlockKind.TOOL | BlockKind.LOG | BlockKind.STATUS:
                return False
            case BlockKind.DIFF | BlockKind.APPROVAL | BlockKind.ERROR | BlockKind.USER | BlockKind.ASSISTANT:
                return True
            case BlockKind.VERIFICATION:
                return status is BlockStatus.FAILED
        return False

    def on_status_change(
        self,
        block: TimelineBlock,
        new_status: BlockStatus,
    ) -> TimelineBlock:
        if block.user_overridden:
            return block.model_copy(update={"status": new_status})
        if new_status is BlockStatus.FAILED and block.status is not BlockStatus.FAILED:
            return block.model_copy(update={"status": new_status, "expanded": True})
        if (
            block.kind is BlockKind.VERIFICATION
            and new_status is BlockStatus.SUCCEEDED
            and not block.user_overridden
        ):
            return block.model_copy(update={"status": new_status, "expanded": False})
        return block.model_copy(update={"status": new_status})

    def with_manual_toggle(self, block: TimelineBlock, expanded: bool) -> TimelineBlock:
        return block.model_copy(update={"expanded": expanded, "user_overridden": True})
