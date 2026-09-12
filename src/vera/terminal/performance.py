"""Timeline budget helpers. Pinned blocks are never evicted."""

from __future__ import annotations

from vera.presentation.timeline import BlockKind, TimelineBlock

PINNED_KINDS = frozenset({BlockKind.APPROVAL, BlockKind.DIFF, BlockKind.ERROR, BlockKind.USER})
MAX_MOUNTED_BLOCKS = 200


def is_pinned(block: TimelineBlock) -> bool:
    return block.kind in PINNED_KINDS


def evictable_ids(
    blocks: tuple[TimelineBlock, ...],
    *,
    limit: int = MAX_MOUNTED_BLOCKS,
) -> tuple[str, ...]:
    if len(blocks) <= limit:
        return ()
    victims: list[str] = []
    overflow = len(blocks) - limit
    for block in blocks:
        if overflow <= 0:
            break
        if is_pinned(block):
            continue
        victims.append(block.block_id)
        overflow -= 1
    return tuple(victims)
