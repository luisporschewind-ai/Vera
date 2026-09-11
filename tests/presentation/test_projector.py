from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame, StreamFrameType
from vera.presentation.projector import AppendBlock, FocusBlock, TimelineProjector, UpdateBlock
from vera.presentation.timeline import BlockKind


def event(
    event_type: str,
    *,
    run_id: str = "run_1",
    sequence: int = 1,
    payload: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{sequence}",
        run_id=run_id,
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def assistant_delta(stream_id: str, index: int, text: str) -> StreamFrame:
    return StreamFrame(
        run_id="run_1",
        stream_id=stream_id,
        index=index,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": text},
    )


def only_appended_block(mutations):  # type: ignore[no-untyped-def]
    appends = [item.block for item in mutations if isinstance(item, AppendBlock)]
    assert len(appends) == 1
    return appends[0]


def test_changeset_and_approval_are_expanded() -> None:
    projector = TimelineProjector()
    diff = only_appended_block(
        projector.apply(
            event(
                "changeset.proposed",
                payload={
                    "files": [
                        {"path": "a.py", "unified_diff": "--- a/a.py\n+++ b/a.py\n+hi\n"}
                    ]
                },
            )
        )
    )
    approval_mutations = projector.apply(
        event("approval.required", sequence=2, payload={"approval_id": "a1", "risk": "low"})
    )
    approval = only_appended_block(approval_mutations)
    assert diff.kind is BlockKind.DIFF and diff.expanded is True
    assert approval.kind is BlockKind.APPROVAL and approval.expanded is True
    assert isinstance(approval_mutations[-1], FocusBlock)


def test_duplicate_delta_is_ignored() -> None:
    projector = TimelineProjector()
    frame = assistant_delta(stream_id="s1", index=0, text="你")
    first = projector.apply(frame)
    second = projector.apply(frame)
    assert first
    assert second == ()


def test_gap_marks_incomplete_and_stops_deltas() -> None:
    projector = TimelineProjector()
    projector.apply(assistant_delta("s1", 0, "a"))
    gap = projector.apply(assistant_delta("s1", 2, "c"))
    assert gap and isinstance(gap[0], UpdateBlock)
    assert gap[0].block.incomplete is True
    assert projector.apply(assistant_delta("s1", 3, "d")) == () or gap[0].block.incomplete


def test_tool_failure_expands_existing_block() -> None:
    projector = TimelineProjector()
    started = only_appended_block(
        projector.apply(event("tool.started", payload={"name": "read_file", "call_id": "c1"}))
    )
    assert started.expanded is False
    updated = projector.apply(
        event(
            "tool.completed",
            sequence=2,
            payload={"name": "read_file", "call_id": "c1", "ok": False, "error": "boom"},
        )
    )
    assert isinstance(updated[0], UpdateBlock)
    assert updated[0].block.expanded is True
    assert updated[0].block.status.value == "failed"


def test_assistant_message_replaces_stream_body() -> None:
    projector = TimelineProjector()
    projector.apply(assistant_delta("s1", 0, "partial"))
    mutations = projector.apply(
        event(
            "assistant.message",
            sequence=2,
            payload={"content": "final text", "stream_id": "s1"},
        )
    )
    assert isinstance(mutations[0], UpdateBlock)
    assert mutations[0].block.body == "final text"
    assert mutations[0].block.incomplete is False
