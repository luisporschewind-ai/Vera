"""In-memory state for a run paused at an approval boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from vera.content.envelope import ContentFinding
from vera.contracts.checkpoints import CheckpointManifest
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryPlan
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelMessage, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate
from vera.runtime.state import RunStateMachine
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


def compact_run_messages(
    messages: list[ModelMessage],
    *,
    max_bytes: int,
    max_tool_messages: int = 8,
) -> list[ModelMessage]:
    tool_indexes = [index for index, message in enumerate(messages) if message.role == "tool"]
    keep = set(tool_indexes[-max_tool_messages:])
    dropped = 0
    compacted: list[ModelMessage] = []
    insert_at = 0
    for index, message in enumerate(messages):
        if message.role == "system":
            compacted.append(message)
            insert_at = len(compacted)
            continue
        if message.role == "tool" and index not in keep:
            dropped += 1
            continue
        compacted.append(message)
    if dropped:
        compacted.insert(
            insert_at,
            ModelMessage(
                role="tool",
                content=(
                    '{"content_hash":"","notice":"dropped untrusted tool results",'
                    f'"count":{dropped},"vera_content":1}}'
                ),
            ),
        )
    used = sum(len(message.content.encode("utf-8")) for message in compacted)
    if used <= max_bytes:
        return compacted
    return [
        message.model_copy(update={"content": _omit_untrusted_body(message.content)})
        if message.role == "tool"
        else message
        for message in compacted
    ]


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
    verification_index: int = 0
    verification_failed: bool = False
    repeated_calls: dict[str, int] = field(default_factory=dict)
    checkpoint_manifest: CheckpointManifest | None = None
    workspace_write_started: bool = False
    snapshot_created_at: datetime | None = None
    pending_recovery_plan: RecoveryPlan | None = None
    security_findings: tuple[ContentFinding, ...] = ()
    security_context_hash: str | None = None
    findings_truncated: bool = False
