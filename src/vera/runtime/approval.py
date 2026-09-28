"""One-time approval gate for changesets and commands."""

from enum import StrEnum
from typing import Literal
from uuid import uuid4

from vera.content.envelope import ContentEnvelope
from vera.contracts.approvals import ApprovalRequest
from vera.contracts.commands import ResolveApproval


class ApprovalKind(StrEnum):
    CHANGESET = "changeset"
    COMMAND = "command"
    TOOL = "tool"
    RECOVERY = "recovery"


class ApprovalMismatch(ValueError):
    """Raised for replayed, stale, or cross-run approval commands."""

    def __init__(self, message: str, *, reason: str = "unknown_approval") -> None:
        super().__init__(message)
        self.reason = reason


class ApprovalGate:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.pending_approval: ApprovalRequest | None = None

    def require(
        self,
        kind: ApprovalKind,
        target_id: str,
        target_hash: str,
        description: str,
        risk: Literal["low", "medium", "high"],
        *,
        workspace_identity: str | None = None,
        policy_hash: str | None = None,
        fact_hash: str | None = None,
        security_context_hash: str | None = None,
        risk_labels: tuple[str, ...] = (),
        risk_sources: tuple[ContentEnvelope, ...] = (),
        available_scopes: tuple[Literal["once", "run", "workspace"], ...] = (
            "once",
            "run",
            "workspace",
        ),
    ) -> ApprovalRequest:
        if self.pending_approval is not None:
            raise ApprovalMismatch("an approval is already pending", reason="duplicate_pending")
        request = ApprovalRequest(
            approval_id=f"approval_{uuid4().hex}",
            run_id=self.run_id,
            kind=kind.value,
            target_id=target_id,
            target_hash=target_hash,
            description=description,
            risk=risk,
            workspace_identity=workspace_identity,
            policy_hash=policy_hash,
            fact_hash=fact_hash,
            security_context_hash=security_context_hash,
            risk_labels=risk_labels,
            risk_sources=risk_sources,
            available_scopes=available_scopes,
        )
        self.pending_approval = request
        return request

    def resolve(self, command: ResolveApproval) -> str:
        request = self.pending_approval
        if request is None or command.approval_id != request.approval_id:
            raise ApprovalMismatch(
                "approval does not match pending request",
                reason="unknown_approval",
            )
        if command.run_id != self.run_id or command.run_id != request.run_id:
            raise ApprovalMismatch(
                "approval does not match pending request",
                reason="cross_run",
            )
        if command.target_hash != request.target_hash:
            raise ApprovalMismatch(
                "approval does not match pending request",
                reason="target_hash_changed",
            )
        self.pending_approval = None
        return command.decision

    @classmethod
    def restore(cls, request: ApprovalRequest) -> "ApprovalGate":
        gate = cls(request.run_id)
        gate.pending_approval = request
        return gate
