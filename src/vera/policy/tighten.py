"""Risk facts may only keep or tighten a PolicyEngine decision."""

from __future__ import annotations

from vera.content.detector import KNOWN_RISK_LABELS, DetectionDisposition
from vera.policy.models import PolicyDecision, PolicyDecisionKind

_SEVERE = frozenset(
    {
        DetectionDisposition.QUARANTINE,
        DetectionDisposition.BLOCK,
        DetectionDisposition.UNAVAILABLE,
    }
)


def tighten_policy_decision(
    base: PolicyDecision,
    risk_labels: tuple[str, ...],
    detector_disposition: str,
) -> PolicyDecision:
    if base.decision is PolicyDecisionKind.DENY:
        return base
    disposition, known = _parse_disposition(detector_disposition)
    unknown_labels = any(label not in KNOWN_RISK_LABELS for label in risk_labels)
    if (not known) or disposition in _SEVERE:
        return _copy(
            base,
            PolicyDecisionKind.DENY,
            "risk_tightened",
            "risk detector tightened this action to deny",
        )
    warn_like = disposition is DetectionDisposition.WARN or unknown_labels
    if warn_like:
        if base.decision is PolicyDecisionKind.ALLOW:
            return _copy(
                base,
                PolicyDecisionKind.APPROVAL_REQUIRED,
                "risk_tightened",
                "risk detector requires explicit approval",
            )
        return base
    return base


def _parse_disposition(value: str) -> tuple[DetectionDisposition, bool]:
    try:
        return DetectionDisposition(value), True
    except ValueError:
        return DetectionDisposition.UNAVAILABLE, False


def _copy(
    base: PolicyDecision,
    decision: PolicyDecisionKind,
    reason_code: str,
    reason: str,
) -> PolicyDecision:
    return base.model_copy(
        update={
            "decision": decision,
            "reason_code": reason_code,
            "reason": reason,
            "matched_rule": "risk_tighten",
        }
    )
