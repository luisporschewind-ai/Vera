"""Phase 9 event facts stay equal across JSON, human and timeline clients."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.skills.test_manifest import write_skill
from tests.terminal.test_app import make_controller
from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import format_skill_event
from vera.presentation.projector import AppendBlock, TimelineProjector
from vera.presentation.timeline import BlockKind
from vera.session.actions import ExecuteSlashCommand
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService


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


def test_skill_listed_uses_same_safe_public_summary_for_clients(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    user = tmp_path / "user"
    user.mkdir()
    write_skill(user)
    controller.dependencies.runtime.skill_selection_service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )

    listed = next(
        item
        for item in controller.dispatch(ExecuteSlashCommand(raw="/skills"))
        if isinstance(item, EventEnvelope) and item.type == "skill.listed"
    )
    plain = format_skill_event(listed.payload)
    blocks = TimelineProjector().apply(listed)
    timeline = next(item.block for item in blocks if isinstance(item, AppendBlock))
    json_payload = json.loads(listed.model_dump_json())["payload"]

    assert listed.payload["items"][0]["skill_id"] == "user:python-review"
    assert json_payload["items"] == listed.payload["items"]
    assert "python-review" in plain
    assert "python-review" in timeline.body
    assert "# Skill" not in str(listed.payload)
    assert str(tmp_path) not in str(listed.payload)
    assert "\x1b" not in str(listed.payload) + plain + timeline.body
