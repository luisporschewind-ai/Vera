from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import format_skill_event
from vera.presentation.projector import AppendBlock, TimelineProjector
from vera.presentation.timeline import BlockKind


def test_skill_projection_is_structured_and_body_free() -> None:
    event = EventEnvelope(
        event_id="e1",
        run_id="session",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="skill.listed",
        payload={
            "items": [
                {
                    "skill_id": "user:python-review",
                    "name": "python-review",
                    "source_kind": "user",
                    "version": "1.0.0",
                    "availability": "available",
                }
            ],
            "text": "Skills：\n- python-review [user] 1.0.0 · available",
        },
    )
    mutations = TimelineProjector().apply(event)
    block = next(item.block for item in mutations if isinstance(item, AppendBlock))

    assert block.kind is BlockKind.STATUS
    assert "python-review" in block.body
    assert "SKILL.md" not in block.body
    assert "secret body" not in format_skill_event(event.payload)
