"""In-memory state for a run paused at an approval boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from vera.contracts.checkpoints import CheckpointManifest
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryPlan
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelMessage, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.presentation.sanitize import sanitize_terminal_text
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate
from vera.runtime.state import RunStateMachine
from vera.tools.definitions import ToolResult
from vera.workspace.changeset import BuiltChangeSet


def tool_result_message(call: ModelToolCall, result: ToolResult) -> str:
    path = ""
    if isinstance(call.arguments, dict) and call.arguments.get("path") is not None:
        path = str(call.arguments.get("path"))
    text = str(result.content or "")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    preview = sanitize_terminal_text(text[:240])
    header = (
        f"[tool_ref name={call.name} path={path} sha256={digest} "
        f"bytes={len(text.encode('utf-8'))} truncated={str(bool(result.truncated)).lower()}]"
    )
    return str(Redactor().redact(f"{header}\n{preview}"))


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
                content=f"[tool_ref_summary count={dropped} truncated=true]",
            ),
        )
    used = sum(len(message.content.encode("utf-8")) for message in compacted)
    if used <= max_bytes:
        return compacted
    return [
        message.model_copy(update={"content": message.content.split("\n", 1)[0]})
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
