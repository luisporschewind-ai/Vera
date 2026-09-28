import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from vera.content.envelope import (
    build_content_envelope,
    render_content_for_model,
    render_project_guidance_for_model,
)
from vera.contracts.commands import StartRun
from vera.contracts.conversation import ConversationMessage
from vera.models.base import ModelMessage, ModelRequest, ModelToolCall
from vera.project_instructions import ProjectInstructionSet, ProjectInstructionSource
from vera.tools.definitions import ToolDefinition
from vera.trace.context_inventory import ContextInventory


def _canonical(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")  # type: ignore[union-attr]
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _wrapped(text: str, *, source_kind: str, origin: str) -> str:
    envelope = build_content_envelope(text, source_kind=source_kind, origin=origin)
    return render_content_for_model(envelope, text)


def _context() -> SimpleNamespace:
    guide = "guide body secret"
    guide_hash = hashlib.sha256(guide.encode("utf-8")).hexdigest()
    source = ProjectInstructionSource(
        name="VERA.md",
        content=guide,
        content_hash=guide_hash,
        byte_count=len(guide.encode("utf-8")),
        priority=20,
    )
    conversation = (
        ConversationMessage(role="user", content="conversation user secret"),
        ConversationMessage(role="assistant", content="conversation assistant secret"),
        ConversationMessage(role="summary", content="compaction summary secret"),
    )
    command = StartRun(
        goal="initial user goal secret",
        workspace_root=Path("/private/project"),
        model_profile="fake",
        conversation=conversation,
    )
    skill_text = "skill content secret"
    skill_envelope = build_content_envelope(
        skill_text, source_kind="skill_content", origin="private/path/SKILL.md"
    )
    return SimpleNamespace(
        command=command,
        project_instructions=ProjectInstructionSet(
            sources=(source,), issues=(), guidance_hash=guide_hash
        ),
        skill_context=(SimpleNamespace(envelope=skill_envelope, text=skill_text),),
        skill_snapshot=SimpleNamespace(snapshot_id="private-snapshot-id"),
    )


def _classified_request() -> tuple[ModelRequest, SimpleNamespace]:
    context = _context()
    guide = context.project_instructions.sources[0]
    guide_envelope = build_content_envelope(
        guide.content,
        source_kind="project_guidance",
        origin=guide.name,
    )
    project_message = render_project_guidance_for_model(
        [(guide_envelope, guide.content, guide.priority)]
    )
    skill_part = context.skill_context[0]
    messages = (
        ModelMessage(role="system", content="system prompt"),
        ModelMessage(role="user", content=project_message),
        ModelMessage(
            role="user",
            content=_wrapped(
                skill_part.text,
                source_kind="skill_content",
                origin="private/path/SKILL.md",
            ),
        ),
        ModelMessage(
            role="user",
            content=_wrapped(
                context.command.conversation[0].content,
                source_kind="user_goal",
                origin="conversation.user",
            ),
        ),
        ModelMessage(
            role="assistant",
            content=_wrapped(
                context.command.conversation[1].content,
                source_kind="model_output",
                origin="conversation.assistant",
            ),
        ),
        ModelMessage(
            role="assistant",
            content=_wrapped(
                context.command.conversation[2].content,
                source_kind="conversation_summary",
                origin="conversation.summary",
            ),
        ),
        ModelMessage(
            role="user",
            content=_wrapped(
                context.command.goal,
                source_kind="user_goal",
                origin="start_run.goal",
            ),
        ),
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=(
                ModelToolCall(call_id="call_1", name="read_file", arguments={"path": "x"}),
            ),
        ),
        ModelMessage(
            role="tool",
            content=_wrapped("tool result secret", source_kind="tool_output", origin="file"),
            tool_call_id="call_1",
        ),
        ModelMessage(role="user", content="unclassified context"),
    )
    tools = (
        ToolDefinition(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        ),
    )
    return ModelRequest(messages=messages, tools=tools, max_output_tokens=64), context


def test_context_inventory_classifies_request_and_counts_exact_canonical_bytes() -> None:
    request, context = _classified_request()

    snapshot = ContextInventory.build(
        request, context, request_index=1, context_budget_bytes=65_536
    )

    kinds = {item.kind for item in snapshot.by_kind}
    assert kinds == {
        "system",
        "project_guidance",
        "skill",
        "conversation",
        "user_input",
        "assistant_tool_call",
        "tool_result",
        "compaction_summary",
        "tool_schema",
        "other",
    }
    assert snapshot.message_count == len(request.messages)
    assert snapshot.tool_schema_count == len(request.tools)
    assert snapshot.total_bytes == sum(
        len(_canonical(item)) for item in (*request.messages, *request.tools)
    )
    assert sum(item.byte_count for item in snapshot.by_kind) == snapshot.total_bytes
    assert sum(item.entry_count for item in snapshot.by_kind) == len(request.messages) + len(
        request.tools
    )

    serialized = snapshot.model_dump_json()
    for secret in (
        "system prompt",
        "guide body secret",
        "skill content secret",
        "conversation user secret",
        "initial user goal secret",
        '"path":"x"',
        "tool result secret",
    ):
        assert secret not in serialized
    assert all(len(part.content_hash) == 64 for part in snapshot.parts)


def test_context_inventory_groups_exact_repeats_but_keeps_distinct_sources() -> None:
    context = _context()
    context.command = context.command.model_copy(
        update={
            "goal": "same body",
            "conversation": (ConversationMessage(role="user", content="same body"),),
        }
    )
    duplicate = ModelMessage(role="system", content="repeated system")
    request = ModelRequest(
        messages=(
            duplicate,
            duplicate,
            ModelMessage(
                role="user",
                content=_wrapped(
                    "same body",
                    source_kind="user_goal",
                    origin="start_run.goal",
                ),
            ),
            ModelMessage(
                role="user",
                content=_wrapped(
                    "same body",
                    source_kind="user_goal",
                    origin="conversation.user",
                ),
            ),
        ),
        max_output_tokens=32,
    )

    snapshot = ContextInventory.build(request, context, request_index=1, context_budget_bytes=100)
    system = next(part for part in snapshot.parts if part.kind == "system")
    assert system.occurrence_count == 2
    assert system.message_count == 2
    assert system.byte_count == 2 * len(_canonical(duplicate))
    same_body = [part for part in snapshot.parts if part.content_hash != system.content_hash]
    assert len(same_body) == 2
    assert len({part.source_ref for part in same_body}) == 2

    next_snapshot = ContextInventory.build(
        request, context, request_index=2, context_budget_bytes=100
    )
    assert next_snapshot.parts == snapshot.parts
    assert next_snapshot.request_index == 2
    assert next_snapshot.snapshot_id != snapshot.snapshot_id


def test_context_inventory_omits_entries_deterministically_at_part_limit() -> None:
    context = _context()
    messages = tuple(
        ModelMessage(role="system", content=f"system-{index:03d}") for index in range(260)
    )
    request = ModelRequest(messages=messages, max_output_tokens=16)

    snapshot = ContextInventory.build(request, context, request_index=1, context_budget_bytes=1)
    repeated = ContextInventory.build(request, context, request_index=1, context_budget_bytes=1)

    assert len(snapshot.parts) == 256
    assert snapshot.truncated is True
    assert snapshot.omitted_entry_count == 4
    assert snapshot.omitted_bytes == sum(len(_canonical(item)) for item in messages[-4:])
    assert snapshot.total_bytes == sum(len(_canonical(item)) for item in messages)
    assert snapshot.model_copy(update={"snapshot_id": "stable"}) == repeated.model_copy(
        update={"snapshot_id": "stable"}
    )


def test_context_inventory_omits_whole_parts_to_keep_snapshot_json_within_byte_limit() -> None:
    context = _context()
    tools = tuple(
        ToolDefinition(
            name=f"tool_{'x' * 120}_{index:03d}",
            description="A tool",
            input_schema={"type": "object"},
        )
        for index in range(256)
    )
    request = ModelRequest(messages=(), tools=tools, max_output_tokens=16)

    snapshot = ContextInventory.build(request, context, request_index=1, context_budget_bytes=1)
    encoded = _canonical(snapshot.model_dump(mode="json"))

    assert len(encoded) <= 65_536
    assert 0 < len(snapshot.parts) < len(tools)
    assert snapshot.truncated is True
    omitted_tools = [
        tool
        for tool in tools
        if f"tool_schema:{tool.name}" not in {part.source_ref for part in snapshot.parts}
    ]
    assert snapshot.omitted_entry_count == len(omitted_tools)
    assert snapshot.omitted_bytes == sum(len(_canonical(tool)) for tool in omitted_tools)
    assert snapshot.total_bytes == sum(len(_canonical(item)) for item in tools)
