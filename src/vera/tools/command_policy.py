"""Classify verification commands before they reach the host process table."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vera.contracts.verification import VerificationCommand
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecisionKind
from vera.policy.snapshot import EffectivePolicySnapshot, normalize_prefixes


class CommandDecisionKind(StrEnum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class CommandDecision:
    kind: CommandDecisionKind
    reason: str
    reason_code: str = ""
    policy_hash: str = ""


_KIND_MAP = {
    PolicyDecisionKind.ALLOW: CommandDecisionKind.ALLOWED,
    PolicyDecisionKind.APPROVAL_REQUIRED: CommandDecisionKind.APPROVAL_REQUIRED,
    PolicyDecisionKind.DENY: CommandDecisionKind.FORBIDDEN,
}


class CommandPolicy:
    def __init__(
        self,
        user_allowed_prefixes: tuple[tuple[str, ...], ...] = (),
        *,
        policy_engine: PolicyEngine | None = None,
        workspace_identity: str = "default",
    ) -> None:
        self.user_allowed_prefixes = normalize_prefixes(user_allowed_prefixes)
        self.workspace_identity = workspace_identity
        self.engine = policy_engine or PolicyEngine(
            EffectivePolicySnapshot(
                workspace_identity=workspace_identity,
                user_allowed_command_prefixes=self.user_allowed_prefixes,
            )
        )

    def classify(self, command: VerificationCommand) -> CommandDecision:
        decision = self.engine.decide(
            PolicyAction(
                kind=PolicyActionKind.COMMAND_EXECUTE,
                workspace_identity=self.workspace_identity,
                resource=command.argv[0] if command.argv else "",
                argv=command.argv,
                metadata={"cwd": command.cwd},
            )
        )
        return CommandDecision(
            kind=_KIND_MAP[decision.decision],
            reason=decision.reason,
            reason_code=decision.reason_code,
            policy_hash=decision.policy_hash,
        )
