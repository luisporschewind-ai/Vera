"""In-memory state for a run paused at an approval boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from vera.content.envelope import ContentFinding
from vera.contracts.checkpoints import CheckpointManifest
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryPlan
from vera.contracts.skills import SkillSnapshot
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelMessage, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.project_instructions import ProjectInstructionSet
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate
from vera.runtime.state import RunStateMachine
from vera.skills.context import SkillContextPart
from vera.tools.definitions import ToolResult
from vera.workspace.changeset import BuiltChangeSet


def tool_result_message(call: ModelToolCall, result: ToolResult, rendered: str) -> str:
    del call, result
    return str(Redactor().redact(rendered))


def _omit_untrusted_body(content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return content.split("\n", 1)[0]
    if not isinstance(payload, dict):
        return content.split("\n", 1)[0]
    payload["data"] = ""
    payload["truncated"] = True
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


_DROPPED_TOOL_NOTICE = "dropped untrusted tool results"


def _dropped_notice_count(message: ModelMessage) -> int:
    if message.role != "user":
        return 0
    try:
        payload = json.loads(message.content)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict) or payload.get("notice") != _DROPPED_TOOL_NOTICE:
        return 0
    raw = payload.get("count")
    return raw if isinstance(raw, int) and raw > 0 else 0


def _tool_rounds(messages: list[ModelMessage]) -> list[tuple[int, list[int]]]:
    """Group each assistant.tool_calls turn with the tool results that follow it."""

    rounds: list[tuple[int, list[int]]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == "assistant" and message.tool_calls:
            tools: list[int] = []
            cursor = index + 1
            while cursor < len(messages) and messages[cursor].role == "tool":
                tools.append(cursor)
                cursor += 1
            rounds.append((index, tools))
            index = cursor
            continue
        index += 1
    return rounds


def normalize_tool_transcript(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Keep only tool results that immediately complete an assistant tool_calls turn."""

    normalized: list[ModelMessage] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == "tool":
            index += 1
            continue
        if message.role != "assistant" or not message.tool_calls:
            normalized.append(message)
            index += 1
            continue
        expected = {call.call_id: call for call in message.tool_calls if call.call_id}
        found: dict[str, ModelMessage] = {}
        cursor = index + 1
        while cursor < len(messages) and messages[cursor].role == "tool":
            tool_id = messages[cursor].tool_call_id
            if tool_id and tool_id in expected and tool_id not in found:
                found[tool_id] = messages[cursor]
            cursor += 1
        if found.keys() == expected.keys():
            normalized.append(message)
            for call in message.tool_calls:
                if call.call_id in found:
                    normalized.append(found[call.call_id])
        else:
            normalized.append(message.model_copy(update={"tool_calls": ()}))
        index = cursor
    return normalized


def _message_bytes(messages: list[ModelMessage]) -> int:
    return sum(len(message.content.encode("utf-8")) for message in messages)


def _omit_tool_bodies(messages: list[ModelMessage]) -> list[ModelMessage]:
    return [
        message.model_copy(update={"content": _omit_untrusted_body(message.content)})
        if message.role == "tool"
        else message
        for message in messages
    ]


def _keep_rounds(
    messages: list[ModelMessage], kept_rounds: list[tuple[int, list[int]]]
) -> list[ModelMessage]:
    keep_assistants = {index for index, _tools in kept_rounds}
    keep_tools = {tool_index for _index, tools in kept_rounds for tool_index in tools}
    compacted: list[ModelMessage] = []
    for index, message in enumerate(messages):
        if message.role == "tool":
            if index in keep_tools:
                compacted.append(message)
            continue
        if message.role == "assistant" and message.tool_calls and index not in keep_assistants:
            continue
        compacted.append(message)
    return compacted


def _drop_oldest_round(messages: list[ModelMessage]) -> tuple[list[ModelMessage], int] | None:
    rounds = _tool_rounds(messages)
    if len(rounds) < 2:
        return None
    assistant_index, tools = rounds[0]
    drop = {assistant_index, *tools}
    return [message for index, message in enumerate(messages) if index not in drop], len(tools)


def _drop_oldest_tool_from_last_round(messages: list[ModelMessage]) -> list[ModelMessage] | None:
    last_assistant: int | None = None
    for index, message in enumerate(messages):
        if message.role == "assistant" and message.tool_calls:
            last_assistant = index
    if last_assistant is None:
        return None
    tool_index = last_assistant + 1
    if tool_index >= len(messages) or messages[tool_index].role != "tool":
        return None
    dropped_id = messages[tool_index].tool_call_id
    assistant = messages[last_assistant]
    remaining = tuple(call for call in assistant.tool_calls if call.call_id != dropped_id)
    if not remaining:
        return [*messages[:last_assistant], *messages[tool_index + 1 :]]
    updated = assistant.model_copy(update={"tool_calls": remaining})
    return [*messages[:last_assistant], updated, *messages[tool_index + 1 :]]


def _insert_drop_notice(messages: list[ModelMessage], dropped: int) -> list[ModelMessage]:
    if dropped <= 0:
        return messages
    insert_at = 0
    for message in messages:
        if message.role != "system":
            break
        insert_at += 1
    notice = ModelMessage(
        role="user",
        content=(
            '{"content_hash":"","notice":"'
            + _DROPPED_TOOL_NOTICE
            + '",'
            + f'"count":{dropped},"vera_content":1}}'
        ),
    )
    return [*messages[:insert_at], notice, *messages[insert_at:]]


def compact_run_messages(
    messages: list[ModelMessage],
    *,
    max_bytes: int,
    max_tool_messages: int = 8,
) -> list[ModelMessage]:
    kept_rounds = list(_tool_rounds(messages))
    dropped = 0
    while len(kept_rounds) > 1 and (
        sum(len(tools) for _index, tools in kept_rounds) > max_tool_messages
    ):
        _index, tools = kept_rounds.pop(0)
        dropped += len(tools)
    compacted = _keep_rounds(messages, kept_rounds)
    dropped += sum(_dropped_notice_count(message) for message in compacted)
    compacted = [message for message in compacted if _dropped_notice_count(message) == 0]
    if _message_bytes(compacted) >= max_bytes:
        compacted = _omit_tool_bodies(compacted)
    while _message_bytes(compacted) >= max_bytes:
        result = _drop_oldest_round(compacted)
        if result is None:
            break
        compacted, removed = result
        dropped += removed
    while _message_bytes(compacted) >= max_bytes:
        nxt = _drop_oldest_tool_from_last_round(compacted)
        if nxt is None:
            break
        compacted = nxt
        dropped += 1
    while True:
        candidate = _insert_drop_notice(compacted, dropped)
        if _message_bytes(candidate) < max_bytes:
            return normalize_tool_transcript(candidate)
        nxt = _drop_oldest_tool_from_last_round(compacted)
        if nxt is None:
            return normalize_tool_transcript(candidate)
        compacted = nxt
        dropped += 1


@dataclass
class RunContext:
    run_id: str
    command: StartRun
    machine: RunStateMachine
    journal: EventJournal
    messages: list[ModelMessage]
    approval_gate: ApprovalGate
    model_turns: int = 0
    tool_calls: int = 0
    context_bytes: int = 0
    built_change_set: BuiltChangeSet | None = None
    pending_command: VerificationCommand | None = None
    """Planned VerificationCommand waiting for command approval; never a second derived copy."""
    verification_index: int = 0
    verification_failed: bool = False
    last_tool_signature: str | None = None
    repeated_tool_streak: int = 0
    checkpoint_manifest: CheckpointManifest | None = None
    workspace_write_started: bool = False
    snapshot_created_at: datetime | None = None
    pending_recovery_plan: RecoveryPlan | None = None
    security_findings: tuple[ContentFinding, ...] = ()
    security_context_hash: str | None = None
    findings_truncated: bool = False
    project_instructions: ProjectInstructionSet | None = None
    empty_after_tools_nudge: bool = False
    claimed_changeset_nudge: bool = False
    skill_snapshot: SkillSnapshot | None = None
    skill_context: tuple[SkillContextPart, ...] = ()
