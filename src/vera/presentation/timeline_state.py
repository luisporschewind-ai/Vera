"""Timeline state mutation helpers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from vera.contracts.events import EventEnvelope
from vera.presentation.errors import SideEffectFact
from vera.presentation.mutations import AppendBlock, FocusBlock, TimelineMutation, UpdateBlock
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock

if TYPE_CHECKING:
    from vera.presentation.projector import TimelineProjector
from vera.presentation.timeline_time import should_omit_timeline_block


def with_occurred_at(
    host: TimelineProjector, mutations: tuple[TimelineMutation, ...], occurred_at: datetime
) -> tuple[TimelineMutation, ...]:
    stamped: list[TimelineMutation] = []
    for item in mutations:
        if isinstance(item, (AppendBlock, UpdateBlock)) and item.block.occurred_at is None:
            block = item.block.model_copy(
                update={"occurred_at": occurred_at, "created_at": occurred_at}
            )
            host._blocks[block.block_id] = block
            item = item.model_copy(update={"block": block})
        stamped.append(item)
    return tuple(stamped)


def side_effects_for(host: TimelineProjector, run_id: str) -> SideEffectFact:
    """Only claim a side effect when a write or command event was observed."""

    return "workspace_changed" if run_id in host._side_effect_runs else "no_workspace_change"


def unapplied_diffs(host: TimelineProjector, run_id: str) -> tuple[TimelineMutation, ...]:
    """Keep proposal Diff visible, but never imply the workspace was written."""

    if run_id in host._side_effect_runs:
        return ()
    return host._relabel_diffs(run_id, title="Diff · 未写入", status=BlockStatus.FAILED)


def relabel_diffs(
    host: TimelineProjector,
    run_id: str,
    *,
    title: str,
    status: BlockStatus,
) -> tuple[TimelineMutation, ...]:
    mutations: list[TimelineMutation] = []
    for key, block in list(host._blocks.items()):
        if block.run_id != run_id or block.kind is not BlockKind.DIFF:
            continue
        updated = block.model_copy(
            update={
                "title": sanitize_terminal_text(title),
                "status": status,
            }
        )
        host._blocks[key] = updated
        mutations.append(UpdateBlock(block=updated))
    return tuple(mutations)


def changeset_applied(
    host: TimelineProjector, event: EventEnvelope
) -> tuple[TimelineMutation, ...]:
    return host._relabel_diffs(
        event.run_id,
        title="Diff · 已写入",
        status=BlockStatus.SUCCEEDED,
    ) + host._status_event(event)


def truncate_body(host: TimelineProjector, body: str) -> tuple[str, bool]:
    encoded = body.encode("utf-8")
    if len(encoded) <= host._max_body_bytes:
        return body, False
    clipped = encoded[: host._max_body_bytes].decode("utf-8", errors="ignore")
    return clipped, True


def evict_if_needed(host: TimelineProjector) -> None:
    protected = {BlockKind.APPROVAL, BlockKind.DIFF, BlockKind.ERROR, BlockKind.USER}
    while len(host._blocks) > host._max_blocks:
        victim = next(
            (key for key, block in host._blocks.items() if block.kind not in protected),
            None,
        )
        if victim is None:
            break
        del host._blocks[victim]


def append(
    host: TimelineProjector,
    *,
    block_id: str,
    run_id: str,
    kind: BlockKind,
    title: str,
    body: str,
    status: BlockStatus,
    focus: bool = False,
    ref_id: str | None = None,
    occurred_at: datetime | None = None,
) -> tuple[TimelineMutation, ...]:
    expanded = host.disclosure.initial_state(kind, status)
    clipped, truncated = host._truncate_body(sanitize_terminal_text(body))
    previous = next(reversed(host._blocks.values()), None) if host._blocks else None
    if should_omit_timeline_block(kind, title, clipped, previous=previous):
        return ()
    block = TimelineBlock(
        block_id=block_id,
        run_id=run_id,
        kind=kind,
        title=sanitize_terminal_text(title),
        body=clipped,
        status=status,
        expanded=expanded,
        truncated=truncated,
        ref_id=ref_id,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )
    host._blocks[block_id] = block
    host._evict_if_needed()
    mutations: list[TimelineMutation] = [AppendBlock(block=block)]
    if focus:
        mutations.append(FocusBlock(block_id=block_id))
    return tuple(mutations)


class TimelineState:
    """Stable façade for timeline state operations."""

    with_occurred_at = staticmethod(with_occurred_at)
    side_effects_for = staticmethod(side_effects_for)
    unapplied_diffs = staticmethod(unapplied_diffs)
    relabel_diffs = staticmethod(relabel_diffs)
    changeset_applied = staticmethod(changeset_applied)
    truncate_body = staticmethod(truncate_body)
    evict_if_needed = staticmethod(evict_if_needed)
    append = staticmethod(append)
