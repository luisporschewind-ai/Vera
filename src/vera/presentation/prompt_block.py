"""User-prompt timeline block projection."""

from __future__ import annotations

from datetime import datetime

from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock


def project_user_prompt(
    run_id: str,
    text: str,
    sequence: int = 0,
    *,
    created_at: datetime | None = None,
    occurred_at: datetime | None = None,
) -> TimelineBlock:
    policy = DisclosurePolicy()
    stamp = occurred_at if occurred_at is not None else created_at
    return TimelineBlock(
        block_id=f"{run_id}:{sequence}:user",
        run_id=run_id,
        kind=BlockKind.USER,
        title="用户",
        body=sanitize_terminal_text(text),
        status=BlockStatus.SUCCEEDED,
        expanded=policy.initial_state(BlockKind.USER, BlockStatus.SUCCEEDED),
        occurred_at=stamp,
        created_at=stamp,
    )


__all__ = ["project_user_prompt"]
