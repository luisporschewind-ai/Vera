import json
from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import format_skill_event
from vera.presentation.projector import TimelineProjector


def test_skill_event_has_same_structured_facts_for_clients() -> None:
    event = EventEnvelope(
        event_id="e1",
        run_id="session",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="skill.selection.changed",
        payload={
            "selection": {
                "schema_version": 1,
                "mode": "explicit",
                "selector": "user:python-review",
                "status": "selected",
                "skill_id": "user:python-review",
                "source_kind": "user",
                "version": "1.0.0",
                "manifest_hash": "a" * 64,
                "reason_codes": [],
            }
        },
    )
    json_payload = json.loads(event.model_dump_json())
    human = format_skill_event(event.payload)
    timeline = TimelineProjector().apply(event)

    assert json_payload["payload"]["selection"]["skill_id"] == "user:python-review"
    assert "user:python-review" in human
    assert "user:python-review" in str(timeline)
    assert "\x1b" not in event.model_dump_json()
