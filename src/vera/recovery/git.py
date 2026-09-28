"""Small, explicit recovery classifier for native Git commit attempts."""

from __future__ import annotations

from typing import Literal

from vera.contracts import ContractModel


class GitRecoveryDecision(ContractModel):
    plan_id: str
    state: Literal["retry", "recovered", "manual_required"]
    reason_code: Literal["head_unchanged", "commit_proven", "commit_uncertain"]


def classify_commit_recovery(
    *, plan_id: str, current_head: str | None, expected_head: str, result_proven: bool
) -> GitRecoveryDecision:
    if current_head == expected_head:
        return GitRecoveryDecision(
            plan_id=plan_id,
            state="retry",
            reason_code="head_unchanged",
        )
    if result_proven:
        return GitRecoveryDecision(
            plan_id=plan_id,
            state="recovered",
            reason_code="commit_proven",
        )
    return GitRecoveryDecision(
        plan_id=plan_id,
        state="manual_required",
        reason_code="commit_uncertain",
    )
