"""Risk-tiered policy facts and pure v2 decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from vera.contracts import ContractModel, JsonValue
from vera.contracts.tool_actions import FrozenJsonDict, ToolAction, ToolEffect
from vera.policy.models import (
    PolicyDecision,
    PolicyDecisionKind,
    PolicyMode,
    RiskAssessment,
    RiskLevel,
)
from vera.policy.rules import risk_level_for_effect
from vera.policy.tighten import tighten_policy_decision


class PermissionGrant(ContractModel):
    grant_id: str = Field(min_length=1)
    scope: Literal["once", "run", "workspace"]
    tool_name: str = Field(min_length=1)
    effects: tuple[ToolEffect, ...] = Field(min_length=1)
    argument_constraints: dict[str, JsonValue] = Field(min_length=1)
    run_id: str | None = None
    action_id: str | None = None
    action_input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime | None = None

    @field_validator("argument_constraints", mode="after")
    @classmethod
    def freeze_constraints(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return FrozenJsonDict(value)

    @model_validator(mode="after")
    def scope_is_unambiguous(self) -> Self:
        if self.scope == "once" and (
            self.run_id is None or self.action_id is None or self.action_input_hash is None
        ):
            raise ValueError("once grants require run_id, action_id, and action_input_hash")
        if self.scope == "run" and (
            self.run_id is None or self.action_id is not None or self.action_input_hash is not None
        ):
            raise ValueError("run grants require run_id and cannot bind one action")
        if self.scope == "workspace" and (
            self.run_id is not None
            or self.action_id is not None
            or self.action_input_hash is not None
        ):
            raise ValueError("workspace grants cannot bind run or action identity")
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None
        ):
            raise ValueError("expires_at must be timezone-aware")
        return self


class WorkspacePermissionSnapshot(ContractModel):
    schema_version: Literal[1] = 1
    workspace_identity: str = Field(min_length=1)
    policy_major_version: int = Field(gt=0)
    trusted: bool
    protected_roots_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    grants: tuple[PermissionGrant, ...] = ()


class WorkspacePermissionSummary(ContractModel):
    schema_version: Literal[1] = 1
    mode: PolicyMode
    trusted: bool
    rule_summaries: tuple[str, ...]
    snapshot_hash: str


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.FORBIDDEN: 3,
}
_NATIVE_GIT_READ_TOOLS = frozenset(
    {"git_status", "git_diff", "git_log", "git_show", "git_branch_list"}
)


def classify_risk(
    action: ToolAction, permission_snapshot: WorkspacePermissionSnapshot
) -> RiskAssessment:
    if action.workspace_identity != permission_snapshot.workspace_identity:
        return RiskAssessment(
            level=RiskLevel.FORBIDDEN,
            reason_codes=("workspace_identity_mismatch",),
        )
    facts = action.risk_facts
    if facts.outside_workspace or facts.secrets_present or facts.policy_forbidden:
        reason = (
            "outside_workspace"
            if facts.outside_workspace
            else "secrets_present"
            if facts.secrets_present
            else facts.policy_reason_code or "policy_forbidden"
        )
        return RiskAssessment(
            level=RiskLevel.FORBIDDEN,
            reason_codes=(reason,),
        )
    if action.tool_name in _NATIVE_GIT_READ_TOOLS and set(action.effects) == {
        ToolEffect.WORKSPACE_READ,
        ToolEffect.PROCESS_EXECUTE,
    }:
        return RiskAssessment(
            level=RiskLevel.LOW,
            reason_codes=("native_git_read",),
        )
    levels = [
        risk_level_for_effect(effect, trusted=permission_snapshot.trusted)
        for effect in action.effects
    ]
    if facts.protected_target or facts.destructive:
        levels.append(RiskLevel.HIGH)
    if ToolEffect.WORKSPACE_WRITE in action.effects and (
        not facts.facts_complete or not facts.normalized_paths or not facts.recoverable
    ):
        levels.append(RiskLevel.HIGH)
    if ToolEffect.WORKSPACE_READ in action.effects and (
        not facts.facts_complete or not facts.normalized_paths
    ):
        levels.append(RiskLevel.HIGH)
    if ToolEffect.PROCESS_EXECUTE in action.effects and (
        not facts.facts_complete or not facts.argv or facts.cwd is None
    ):
        levels.append(RiskLevel.HIGH)
    level = max(levels, key=_RISK_ORDER.__getitem__) if levels else RiskLevel.FORBIDDEN
    reasons = tuple(f"effect:{effect.value}" for effect in action.effects)
    if not action.effects:
        reasons = ("missing_effect",)
    elif ToolEffect.WORKSPACE_WRITE in action.effects and not permission_snapshot.trusted:
        reasons += ("workspace_untrusted",)
    if not facts.facts_complete:
        reasons += ("risk_facts_incomplete",)
    if facts.protected_target:
        reasons += ("protected_target",)
    if facts.destructive:
        reasons += ("destructive",)
    if facts.external_target is not None:
        reasons += (f"external_target:{facts.external_target}",)
    return RiskAssessment(level=level, reason_codes=reasons)


def decide_v2(
    action: ToolAction,
    permission_snapshot: WorkspacePermissionSnapshot,
    *,
    mode: PolicyMode = PolicyMode.BALANCED,
    goal_authorized: bool,
    risk_labels: tuple[str, ...] = (),
    detector_disposition: str = "clear",
    now: datetime | None = None,
    effective_policy_hash: str | None = None,
) -> PolicyDecision:
    assessment = classify_risk(action, permission_snapshot)
    policy_digest = effective_policy_hash or _policy_hash(mode, permission_snapshot)
    grant = matching_permission_grant(action, permission_snapshot.grants, now=now)

    if assessment.level is RiskLevel.FORBIDDEN:
        base = _decision(
            PolicyDecisionKind.DENY,
            "risk_forbidden",
            "the action crosses a forbidden policy boundary",
            "risk_v2",
            policy_digest,
        )
    elif ToolEffect.APPLE_IOS_BUILD_SERVICES in action.effects:
        base = _decision(
            PolicyDecisionKind.APPROVAL_REQUIRED,
            "apple_build_service_approval_required",
            "Apple build system services require approval for this command",
            "apple_ios_build_services",
            policy_digest,
        )
    elif ToolEffect.FILE_ACCESS_GRANT in action.effects:
        base = _decision(
            PolicyDecisionKind.APPROVAL_REQUIRED,
            "file_access_approval_required",
            "each file access grant requires explicit user approval",
            "file_access",
            policy_digest,
        )
    elif assessment.level is RiskLevel.HIGH:
        if grant is not None and (
            grant.scope in {"once", "run"}
            or (
                action.risk_facts.external_target is None
                and not {
                    ToolEffect.NETWORK_ACCESS,
                    ToolEffect.EXTERNAL_SERVICE,
                }.intersection(action.effects)
            )
        ):
            base = _decision(
                PolicyDecisionKind.ALLOW,
                "permission_grant_matched",
                "a user-created structured permission grant matched",
                f"permission:{grant.scope}",
                policy_digest,
            )
        else:
            base = _decision(
                PolicyDecisionKind.APPROVAL_REQUIRED,
                "high_risk_approval_required",
                "high-risk actions require explicit approval",
                "risk_v2",
                policy_digest,
            )
    elif grant is not None:
        base = _decision(
            PolicyDecisionKind.ALLOW,
            "permission_grant_matched",
            "a user-created structured permission grant matched",
            f"permission:{grant.scope}",
            policy_digest,
        )
    elif action.effects == (ToolEffect.WORKSPACE_READ,):
        base = _decision(
            PolicyDecisionKind.ALLOW,
            "workspace_read_allowed",
            "workspace reads are allowed in every policy mode",
            "risk_v2",
            policy_digest,
        )
    elif action.tool_name in _NATIVE_GIT_READ_TOOLS:
        base = _decision(
            PolicyDecisionKind.ALLOW,
            "native_git_read_allowed",
            "native Git reads are allowed in every policy mode",
            "risk_v2",
            policy_digest,
        )
    elif mode is not PolicyMode.REVIEW and permission_snapshot.trusted and goal_authorized:
        base = _decision(
            PolicyDecisionKind.ALLOW,
            "trusted_goal_action_allowed",
            "the trusted workspace action matches the user goal",
            "risk_v2",
            policy_digest,
        )
    else:
        base = _decision(
            PolicyDecisionKind.APPROVAL_REQUIRED,
            "explicit_approval_required",
            "mode, trust, or user-goal authorization requires approval",
            "risk_v2",
            policy_digest,
        )

    if not risk_labels and detector_disposition == "clear":
        return base
    return tighten_policy_decision(base, risk_labels, detector_disposition)


def permission_summary(
    snapshot: WorkspacePermissionSnapshot,
    *,
    mode: PolicyMode,
) -> WorkspacePermissionSummary:
    rules = tuple(sorted({_grant_summary(grant) for grant in snapshot.grants}))
    return WorkspacePermissionSummary(
        mode=mode,
        trusted=snapshot.trusted,
        rule_summaries=rules,
        snapshot_hash=_policy_hash(mode, snapshot),
    )


def _grant_summary(grant: PermissionGrant) -> str:
    effects = "+".join(effect.value for effect in grant.effects)
    return f"{grant.tool_name}:{effects}:{grant.scope}"


def matching_permission_grant(
    action: ToolAction,
    grants: tuple[PermissionGrant, ...],
    *,
    now: datetime | None,
) -> PermissionGrant | None:
    current = now or datetime.now(UTC)
    for grant in grants:
        if grant.expires_at is not None and grant.expires_at <= current:
            continue
        if grant.tool_name != action.tool_name:
            continue
        if not set(action.effects).issubset(grant.effects):
            continue
        if grant.scope in {"once", "run"} and grant.run_id != action.run_id:
            continue
        if grant.scope == "once" and grant.action_input_hash != action.input_hash:
            continue
        if grant.scope == "once" and grant.action_id != action.action_id:
            continue
        if dict(action.normalized_arguments) != grant.argument_constraints:
            continue
        return grant
    return None


def _decision(
    kind: PolicyDecisionKind,
    reason_code: str,
    reason: str,
    matched_rule: str,
    policy_digest: str,
) -> PolicyDecision:
    return PolicyDecision(
        decision=kind,
        reason_code=reason_code,
        reason=reason,
        matched_rule=matched_rule,
        policy_hash=policy_digest,
    )


def _policy_hash(mode: PolicyMode, snapshot: WorkspacePermissionSnapshot) -> str:
    payload = {
        "mode": mode.value,
        "permission_snapshot": snapshot.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
