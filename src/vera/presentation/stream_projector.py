"""Streaming assistant-output projection flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vera.contracts.streaming import StreamFrame, StreamFrameType
from vera.presentation.mutations import AppendBlock, TimelineMutation, UpdateBlock
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock

if TYPE_CHECKING:
    from vera.presentation.projector import TimelineProjector


def apply(host: TimelineProjector, frame: StreamFrame) -> tuple[TimelineMutation, ...]:
    if frame.type is not StreamFrameType.ASSISTANT_DELTA:
        return ()
    stream_key = f"{frame.run_id}:{frame.stream_id}"
    state = host._streams.setdefault(
        stream_key,
        {"next_index": 0, "text": "", "incomplete": False, "seen": set()},
    )
    seen_raw = state["seen"]
    seen: set[int] = seen_raw if isinstance(seen_raw, set) else set()
    state["seen"] = seen
    if frame.index in seen:
        return ()
    next_raw = state["next_index"]
    next_index = int(next_raw) if isinstance(next_raw, int) else 0
    if bool(state["incomplete"]) or frame.index != next_index:
        state["incomplete"] = True
        block_id = f"{frame.run_id}:{frame.stream_id}:assistant"
        existing = host._blocks.get(block_id)
        if existing is None:
            return ()
        updated = existing.model_copy(update={"incomplete": True})
        host._blocks[block_id] = updated
        return (UpdateBlock(block=updated),)
    seen.add(frame.index)
    state["next_index"] = frame.index + 1
    text = sanitize_terminal_text(str(frame.payload.get("text", "")))
    state["text"] = str(state["text"]) + text
    body, truncated = host._truncate_body(str(state["text"]))
    if truncated:
        state["text"] = body
    block_id = f"{frame.run_id}:{frame.stream_id}:assistant"
    existing = host._blocks.get(block_id)
    if existing is None:
        block = TimelineBlock(
            block_id=block_id,
            run_id=frame.run_id,
            kind=BlockKind.ASSISTANT,
            title="Vera",
            body=body,
            status=BlockStatus.RUNNING,
            expanded=host.disclosure.initial_state(BlockKind.ASSISTANT, BlockStatus.RUNNING),
            truncated=truncated,
        )
        host._blocks[block_id] = block
        return (AppendBlock(block=block),)
    updated = existing.model_copy(
        update={"body": body, "status": BlockStatus.RUNNING, "truncated": truncated}
    )
    host._blocks[block_id] = updated
    return (UpdateBlock(block=updated),)


class StreamProjector:
    """Stable façade for stream-frame projection."""

    apply = staticmethod(apply)
