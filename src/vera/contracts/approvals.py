"""Approval requests emitted by VeraRuntime."""

from typing import Literal

from vera.content.envelope import ContentEnvelope
from vera.contracts import ContractModel


class ApprovalRequest(ContractModel):
    schema_version: Literal[1] = 1
    approval_id: str
    run_id: str
    kind: Literal["changeset", "command", "tool", "recovery"]
    target_id: str
    target_hash: str
    description: str
    risk: Literal["low", "medium", "high"]
    workspace_identity: str | None = None
    policy_hash: str | None = None
    fact_hash: str | None = None
    security_context_hash: str | None = None
    risk_labels: tuple[str, ...] = ()
    risk_sources: tuple[ContentEnvelope, ...] = ()
