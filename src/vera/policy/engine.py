"""UI-independent policy engine."""

from __future__ import annotations

from vera.policy.models import PolicyAction, PolicyDecision, PolicyDecisionKind
from vera.policy.rules import evaluate_rule
from vera.policy.snapshot import EffectivePolicySnapshot, policy_hash
from vera.policy.tighten import tighten_policy_decision


class PolicyEngine:
    def __init__(self, snapshot: EffectivePolicySnapshot) -> None:
        self.snapshot = snapshot
        self._hash = policy_hash(snapshot)

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
