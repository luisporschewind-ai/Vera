"""Classify verification commands before they reach the host process table."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from vera.contracts.process_actions import BashInput
from vera.contracts.tool_actions import ToolEffect
from vera.contracts.verification import VerificationCommand
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecisionKind, RiskLevel
from vera.policy.snapshot import EffectivePolicySnapshot, normalize_prefixes
from vera.tools.bash import classify_argv


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

    def classify(
        self,
        command: VerificationCommand,
        *,
        risk_labels: tuple[str, ...] = (),
        detector_disposition: str | None = None,
    ) -> CommandDecision:
        metadata: dict[str, Any] = {"cwd": command.cwd}
        if detector_disposition is not None or risk_labels:
            metadata["detector_disposition"] = detector_disposition or "clear"
            metadata["risk_labels"] = list(risk_labels)
        decision = self.engine.decide(
            PolicyAction(
                kind=PolicyActionKind.COMMAND_EXECUTE,
                workspace_identity=self.workspace_identity,
                resource=command.argv[0] if command.argv else "",
                argv=command.argv,
                metadata=metadata,
            )
        )
        return CommandDecision(
            kind=_KIND_MAP[decision.decision],
            reason=decision.reason,
            reason_code=decision.reason_code,
            policy_hash=decision.policy_hash,
        )


@dataclass(frozen=True)
class CommandClassification:
    """Stable v2 facts for a structured argv command."""

    executable: str
    risk_level: RiskLevel
    effects: tuple[ToolEffect, ...]
    reason_codes: tuple[str, ...]


class CommandClassifier:
    """Classify argv before policy evaluation; never invokes a shell."""

    def classify(self, argv: tuple[str, ...], *, cwd: str = ".") -> CommandClassification:
        try:
            parsed = BashInput(argv=argv, cwd=cwd)
        except ValidationError:
            executable = argv[0] if argv else ""
            return CommandClassification(
                executable=executable,
                risk_level=RiskLevel.FORBIDDEN,
                effects=(ToolEffect.PROCESS_EXECUTE,),
                reason_codes=("invalid_command",),
            )
        facts = classify_argv(parsed.argv)
        effects: list[ToolEffect] = [ToolEffect.PROCESS_EXECUTE]
        reasons: list[str] = []
        if facts["writes"]:
            effects.append(ToolEffect.WORKSPACE_WRITE)
            reasons.append("workspace_write")
        if facts["network"]:
            effects.append(ToolEffect.NETWORK_ACCESS)
            reasons.append("network_access")
        if facts["installer"]:
            reasons.append("package_install")
        if facts["build"]:
            reasons.append("build_or_verification")
        if facts["service"]:
            reasons.append("background_service")
        if facts["shell"]:
            reasons.append("shell_forbidden")
        if facts["privileged"]:
            reasons.append("privilege_forbidden")
        if facts["destructive"]:
            reasons.append("destructive_forbidden")
        if facts["secret"]:
            reasons.append("secret_access_forbidden")
        if facts["git_write"]:
            reasons.append("use_native_git_tool")
        return CommandClassification(
            executable=str(facts["executable"]),
            risk_level=facts["risk_level"],
            effects=tuple(effects),
            reason_codes=tuple(reasons),
        )
