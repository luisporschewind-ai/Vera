"""Phase 9 event facts stay equal across JSON, human and timeline clients."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import format_skill_event
from vera.presentation.projector import AppendBlock, TimelineProjector
from vera.presentation.timeline import BlockKind


def test_phase_9_client_parity_does_not_promote_skill_body_or_ansi() -> None:
    event = EventEnvelope(
        event_id="skill-e1",
        run_id="session",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="skill.snapshot.bound",
        payload={
            "snapshot_id": "a" * 64,
            "skill_id": "workspace:review",
            "source_kind": "workspace",
            "version": "1.0.0",
            "manifest_hash": "b" * 64,
            "resource_hash": "c" * 64,
        },
    )

    json_payload = json.loads(event.model_dump_json())
    human = format_skill_event(event.payload)
    mutations = TimelineProjector().apply(event)
    block = next(item.block for item in mutations if isinstance(item, AppendBlock))

    assert json_payload["payload"]["skill_id"] == "workspace:review"
    assert "workspace:review" in human
    assert block.kind is BlockKind.STATUS
    assert "workspace:review" in block.body
    assert "SKILL.md" not in json.dumps(json_payload)
    assert "\x1b" not in human + block.body
