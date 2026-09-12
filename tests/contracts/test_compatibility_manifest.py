from __future__ import annotations

import json

import pytest

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.codec import CommandType
from vera.contracts.commands import StartRun
from vera.contracts.compatibility import (
    COMPATIBILITY_RULES,
    CompatibilityManifest,
    current_compatibility_manifest,
    encode_compatibility_manifest,
)
from vera.contracts.errors import CoreErrorCode
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification
from vera.runtime.approval import ApprovalKind
from vera.session.protocol import SessionRecord


def test_compatibility_manifest_is_missing_until_implemented() -> None:
    manifest = current_compatibility_manifest()
    assert isinstance(manifest, CompatibilityManifest)
    assert manifest.schema_version == 1


def test_manifest_snapshots_public_contract_names_and_required_fields() -> None:
    manifest = current_compatibility_manifest()
    command_names = {item.name for item in manifest.commands}
    assert command_names == {item.value for item in CommandType}
    start = next(item for item in manifest.commands if item.name == "start_run")
    assert start.schema_version == 1
    assert "goal" in start.required_fields
    assert "workspace_root" in start.required_fields
    assert "model_profile" in start.required_fields
    assert manifest.event_envelope.name == "event_envelope"
    assert (
        manifest.event_envelope.schema_version
        == EventEnvelope.model_fields["schema_version"].default
    )
    assert "type" in manifest.event_envelope.required_fields
    assert "payload" in manifest.event_envelope.required_fields
    assert set(manifest.runtime_output) == {"event", "stream"}
    assert set(manifest.error_codes) == {item.value for item in CoreErrorCode}
    assert set(manifest.approval_kinds) == {item.value for item in ApprovalKind}
    assert set(manifest.recovery_classifications) == {item.value for item in RecoveryClassification}
    record_types = {item.name for item in manifest.session_records}
    assert record_types == {"event", "stream"}
    action_types = {item.name for item in manifest.session_actions}
    assert action_types == {
        "prompt.submit",
        "session.command",
        "approval.resolve",
        "run.cancel",
        "session.close",
        "prompt.queue",
        "prompt.queue.clear",
        "editor.confirm",
        "editor.open",
    }


def test_manifest_serialization_is_stable_and_excludes_ui_surface() -> None:
    first = encode_compatibility_manifest(current_compatibility_manifest())
    second = encode_compatibility_manifest(current_compatibility_manifest())
    assert first == second
    payload = json.loads(first)
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "textual" not in dumped.lower()
    assert "#composer" not in dumped
    assert "ANSI escape" not in dumped
    assert "Rich markup" not in dumped
    assert payload["compatibility_rules"]["additive"] == COMPATIBILITY_RULES["additive"]
    assert payload["compatibility_rules"]["deprecated"] == COMPATIBILITY_RULES["deprecated"]
    assert payload["compatibility_rules"]["breaking"] == COMPATIBILITY_RULES["breaking"]


def test_public_models_still_round_trip_under_frozen_schema() -> None:
    start = StartRun(goal="edit", workspace_root=".", model_profile="fake")
    restored = StartRun.model_validate_json(start.model_dump_json())
    assert restored.goal == "edit"
    approval = ApprovalRequest(
        approval_id="approval_1",
        run_id="run_1",
        kind="changeset",
        target_id="cs_1",
        target_hash="a" * 64,
        description="edit",
        risk="medium",
    )
    assert ApprovalRequest.model_validate_json(approval.model_dump_json()).kind == "changeset"
    record = SessionRecord.model_validate(
        {
            "record_type": "event",
            "event": {
                "event_id": "e1",
                "run_id": "run_1",
                "sequence": 1,
                "timestamp": "2026-09-13T00:00:00Z",
                "type": "run.started",
                "payload": {},
            },
        }
    )
    assert record.record_type == "event"


def test_unknown_future_command_is_not_silently_accepted() -> None:
    with pytest.raises(ValueError):
        CommandType("not_a_real_command")
