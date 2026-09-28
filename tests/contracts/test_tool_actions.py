from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from vera.contracts.tool_actions import ToolAction, ToolEffect, tool_action_input_hash
from vera.models.base import ModelMessage, ModelRequest
from vera.tools.definitions import ToolDefinitionV2, decode_tool_definition


def test_tool_definition_v2_freezes_execution_metadata() -> None:
    definition = ToolDefinitionV2(
        name="read",
        description="Read a workspace file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        tool_version=2,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=True,
        supports_recovery=True,
        max_output_bytes=100_000,
    )

    assert definition.schema_version == 2
    assert definition.tool_version == 2
    assert definition.effects == (ToolEffect.WORKSPACE_READ,)
    assert definition.max_output_bytes == 100_000
    with pytest.raises(ValidationError):
        ToolDefinitionV2.model_validate(
            {**definition.model_dump(mode="json"), "unexpected": "not additive"}
        )


def test_tool_definition_codec_discriminates_versions_and_model_request_accepts_v2() -> None:
    decoded = decode_tool_definition(
        {
            "schema_version": 2,
            "name": "read",
            "description": "Read",
            "input_schema": {},
            "tool_version": 2,
            "effects": ["workspace_read"],
            "supports_cancellation": True,
            "supports_recovery": True,
            "max_output_bytes": 100_000,
        }
    )
    request = ModelRequest(
        messages=(ModelMessage(role="user", content="read"),),
        tools=(decoded,),
        max_output_tokens=32,
    )

    assert isinstance(decoded, ToolDefinitionV2)
    assert request.tools[0].schema_version == 2
    with pytest.raises(ValidationError):
        decode_tool_definition({"schema_version": 99})


def test_tool_action_round_trips_and_rejects_unknown_fields() -> None:
    normalized = {"path": "src/vera/app.py", "options": {"line": 3, "exact": True}}
    action = ToolAction(
        action_id="action_1",
        run_id="run_1",
        tool_name="read",
        tool_version=2,
        effects=(ToolEffect.WORKSPACE_READ,),
        workspace_identity="workspace_1",
        normalized_arguments=normalized,
        input_hash=tool_action_input_hash(
            tool_name="read",
            tool_version=2,
            workspace_identity="workspace_1",
            effects=(ToolEffect.WORKSPACE_READ,),
            normalized_arguments=normalized,
        ),
    )

    restored = ToolAction.model_validate_json(action.model_dump_json())
    assert restored == action
    with pytest.raises(ValidationError):
        ToolAction.model_validate({**json.loads(action.model_dump_json()), "future": True})


def test_tool_action_input_hash_is_canonical_and_binds_execution_facts() -> None:
    left = tool_action_input_hash(
        tool_name="edit",
        tool_version=2,
        workspace_identity="workspace_1",
        effects=(ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE),
        normalized_arguments={"path": "a.py", "replacement": {"new": "x", "old": "y"}},
    )
    reordered = tool_action_input_hash(
        tool_name="edit",
        tool_version=2,
        workspace_identity="workspace_1",
        effects=(ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE),
        normalized_arguments={"replacement": {"old": "y", "new": "x"}, "path": "a.py"},
    )
    changed = tool_action_input_hash(
        tool_name="edit",
        tool_version=2,
        workspace_identity="workspace_2",
        effects=(ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE),
        normalized_arguments={"path": "a.py", "replacement": {"new": "x", "old": "y"}},
    )

    assert left == reordered
    assert len(left) == 64
    assert left != changed


def test_tool_action_rejects_an_input_hash_that_does_not_bind_its_facts() -> None:
    with pytest.raises(ValidationError):
        ToolAction(
            action_id="action_1",
            run_id="run_1",
            tool_name="read",
            tool_version=2,
            effects=(ToolEffect.WORKSPACE_READ,),
            workspace_identity="workspace_1",
            normalized_arguments={"path": "README.md"},
            input_hash="0" * 64,
        )


def test_tool_action_arguments_are_deeply_immutable_after_hash_validation() -> None:
    normalized = {"argv": ["pytest", "-q"], "env": {"MODE": "test"}}
    action = ToolAction(
        action_id="action_1",
        run_id="run_1",
        tool_name="bash",
        tool_version=2,
        effects=(ToolEffect.PROCESS_EXECUTE,),
        workspace_identity="workspace_1",
        normalized_arguments=normalized,
        input_hash=tool_action_input_hash(
            tool_name="bash",
            tool_version=2,
            workspace_identity="workspace_1",
            effects=(ToolEffect.PROCESS_EXECUTE,),
            normalized_arguments=normalized,
        ),
    )

    with pytest.raises(TypeError):
        action.normalized_arguments["argv"] = ["sudo", "pytest"]
    with pytest.raises(TypeError):
        action.normalized_arguments["env"]["MODE"] = "production"
    assert action.normalized_arguments["argv"] == ("pytest", "-q")


def test_tool_action_hash_rejects_non_standard_json_numbers() -> None:
    with pytest.raises(ValueError):
        tool_action_input_hash(
            tool_name="read",
            tool_version=2,
            workspace_identity="workspace_1",
            effects=(ToolEffect.WORKSPACE_READ,),
            normalized_arguments={"line": math.nan},
        )
