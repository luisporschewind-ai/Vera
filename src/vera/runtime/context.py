"""In-memory state for a run paused at an approval boundary."""

from dataclasses import dataclass, field
from datetime import datetime

from vera.contracts.checkpoints import CheckpointManifest
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryPlan
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelMessage
from vera.persistence.journal import EventJournal
from vera.runtime.approval import ApprovalGate
from vera.runtime.state import RunStateMachine
from vera.workspace.changeset import BuiltChangeSet


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
