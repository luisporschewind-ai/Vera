"""UI-independent policy engine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.tool_actions import ToolAction
from vera.policy.models import PolicyAction, PolicyDecision, PolicyDecisionKind
from vera.policy.permissions import (
    WorkspacePermissionSnapshot,
    decide_v2,
    matching_permission_grant,
)
from vera.policy.rules import evaluate_rule
from vera.policy.snapshot import EffectivePolicySnapshot, EffectivePolicySnapshotV2, policy_hash
from vera.policy.tighten import tighten_policy_decision


class PolicyEngine:
    def __init__(self, snapshot: EffectivePolicySnapshot | EffectivePolicySnapshotV2) -> None:
        self.snapshot = snapshot
        self._hash = policy_hash(snapshot)
        self._consumed_once_grants: set[str] = set()

    @property
    def policy_hash(self) -> str:
        return self._hash

    def decide(self, action: PolicyAction) -> PolicyDecision:
        matched = evaluate_rule(self.snapshot, action)
        if matched is None:
            matched = {
                "decision": PolicyDecisionKind.DENY.value,
                "reason_code": "no_rule",
                "reason": "no matching rule",
                "matched_rule": "none",
            }
        decision = PolicyDecision(
            decision=PolicyDecisionKind(matched["decision"]),
            reason_code=matched["reason_code"],
            reason=matched["reason"],
            matched_rule=matched["matched_rule"],
            policy_hash=self._hash,
        )
        labels = action.metadata.get("risk_labels") or ()
        disposition = action.metadata.get("detector_disposition")
        if disposition is None and not labels:
            return decision
        risk_labels = tuple(str(item) for item in labels)
        detector_disposition = str(disposition) if disposition is not None else "clear"
        return tighten_policy_decision(decision, risk_labels, detector_disposition)

    def decide_tool_action(
        self,
        action: ToolAction,
        permissions: WorkspacePermissionSnapshot,
        *,
        goal_authorized: bool,
        risk_labels: tuple[str, ...] = (),
        detector_disposition: str = "clear",
    ) -> PolicyDecision:
        if not isinstance(self.snapshot, EffectivePolicySnapshotV2):
            return self._v2_deny("policy_v2_required", "tool actions require a v2 policy snapshot")
        if action.workspace_identity != self.snapshot.workspace_identity:
            return self._v2_deny(
                "workspace_identity_mismatch",
                "action workspace does not match the effective policy",
            )
        if (
            permissions.workspace_identity != self.snapshot.workspace_identity
            or permissions.policy_major_version != self.snapshot.builtin_policy_version
            or permissions.protected_roots_hash != self.snapshot.protected_roots_hash
        ):
            return self._v2_deny(
                "permission_snapshot_mismatch",
                "workspace permissions do not bind this effective policy",
            )
        if action.tool_name in self.snapshot.project_denied_tools:
            return self._v2_deny("project_tool_denied", "project policy denies this tool")
        protected = self.snapshot.protected_path_globs + self.snapshot.project_denied_path_globs
        if any(
            Path(path).match(pattern) or Path(path).name == pattern
            for path in action.risk_facts.normalized_paths
            for pattern in protected
        ):
            return self._v2_deny("sensitive_path_forbidden", "policy denies the affected path")
        active_permissions = permissions.model_copy(
            update={
                "grants": tuple(
                    grant
                    for grant in permissions.grants
                    if grant.grant_id not in self._consumed_once_grants
                )
            }
        )
        decided_at = datetime.now(UTC)
        matched_grant = matching_permission_grant(action, active_permissions.grants, now=decided_at)
        decision = decide_v2(
            action,
            active_permissions,
            mode=self.snapshot.policy_mode,
            goal_authorized=goal_authorized,
            risk_labels=risk_labels,
            detector_disposition=detector_disposition,
            now=decided_at,
            effective_policy_hash=self._hash,
        )
        if decision.matched_rule == "permission:once":
            assert matched_grant is not None
            self._consumed_once_grants.add(matched_grant.grant_id)
        return decision

    def _v2_deny(self, reason_code: str, reason: str) -> PolicyDecision:
        return PolicyDecision(
            decision=PolicyDecisionKind.DENY,
            reason_code=reason_code,
            reason=reason,
            matched_rule="policy_v2_binding",
            policy_hash=self._hash,
        )
