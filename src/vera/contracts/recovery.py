"""Public recovery classification and inspection contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

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


class RecoveryPlanFile(ContractModel):
    path: str
    before_hash: str
    after_hash: str
    current_hash: str
    action: Literal["keep_before", "restore_before"]


class RecoveryPlan(ContractModel):
    recovery_id: str
    run_id: str
    workspace_identity: str
    files: tuple[RecoveryPlanFile, ...]
    recovery_hash: str

    @staticmethod
    def compute_hash(workspace_identity: str, files: tuple[RecoveryPlanFile, ...]) -> str:
        payload = {
            "workspace_identity": workspace_identity,
            "files": [
                {
                    "path": item.path,
                    "before_hash": item.before_hash,
                    "after_hash": item.after_hash,
                    "current_hash": item.current_hash,
                    "action": item.action,
                }
                for item in files
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        recovery_id: str,
        run_id: str,
        workspace_identity: str,
        files: tuple[RecoveryPlanFile, ...],
    ) -> RecoveryPlan:
        ordered = tuple(sorted(files, key=lambda item: item.path))
        return cls(
            recovery_id=recovery_id,
            run_id=run_id,
            workspace_identity=workspace_identity,
            files=ordered,
            recovery_hash=cls.compute_hash(workspace_identity, ordered),
        )
