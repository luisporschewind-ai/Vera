"""Approval requests emitted by VeraRuntime."""

from typing import Literal

from vera.contracts import ContractModel


class ApprovalRequest(ContractModel):
    schema_version: Literal[1] = 1
    approval_id: str
    run_id: str
    kind: Literal["changeset", "command", "recovery"]
    target_id: str
    target_hash: str
    description: str
    risk: Literal["low", "medium", "high"]
    workspace_identity: str | None = None
    policy_hash: str | None = None
