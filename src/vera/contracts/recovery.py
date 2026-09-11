"""Public recovery classification and inspection contracts."""

from enum import StrEnum
from pathlib import Path

from vera.contracts import ContractModel


class RecoveryClassification(StrEnum):
    RESUMABLE_APPROVAL = "resumable_approval"
    RESUMABLE_VERIFICATION = "resumable_verification"
    SAFE_TO_ABANDON = "safe_to_abandon"
    RECOVERABLE_PARTIAL_APPLY = "recoverable_partial_apply"
    MANUAL_REQUIRED = "manual_required"
    LEGACY_NOT_RESUMABLE = "legacy_not_resumable"


class FileRecoveryState(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    UNKNOWN = "unknown"


class RecoveryStage(StrEnum):
    STARTED = "started"
    AWAITING_CHANGESET_APPROVAL = "awaiting_changeset_approval"
    CHECKPOINT_READY = "checkpoint_ready"
    AWAITING_VERIFICATION_APPROVAL = "awaiting_verification_approval"
    VERIFYING = "verifying"
    TERMINAL = "terminal"


class RecoveryEvidence(ContractModel):
    path: str
    before_hash: str
    after_hash: str
    current_hash: str
    state: FileRecoveryState


class RecoveryReport(ContractModel):
    run_id: str
    classification: RecoveryClassification
    stage: RecoveryStage
    workspace_root: Path
    evidence: tuple[RecoveryEvidence, ...]
    allowed_actions: tuple[str, ...]
    reason_code: str
