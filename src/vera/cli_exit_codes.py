"""Stable CLI exit codes shared by TUI, Plain, JSON, and one-shot runs."""

from __future__ import annotations

from vera.contracts.events import EventEnvelope

SUCCESS = 0
USER_CANCEL = 2
VERIFICATION_FAILED = 3
PROVIDER_OR_RUN_FAILED = 4
RECOVERY_OR_CONFIG = 5


def exit_code_for_events(events: list[EventEnvelope] | tuple[EventEnvelope, ...]) -> int:
    if not events:
        return RECOVERY_OR_CONFIG
    last = events[-1]
    if last.type == "run.completed":
        if last.payload.get("state") == "verification_failed":
            return VERIFICATION_FAILED
        return SUCCESS
    mapping = {
        "recovery.abandoned": SUCCESS,
        "run.cancelled": USER_CANCEL,
        "run.failed": PROVIDER_OR_RUN_FAILED,
        "rollback.completed": SUCCESS,
        "rollback.conflicted": PROVIDER_OR_RUN_FAILED,
        "recovery.manual_required": RECOVERY_OR_CONFIG,
    }
    if last.type in mapping:
        return mapping[last.type]
    if last.type == "recovery.detected" and last.payload.get("classification") in {
        "manual_required",
        "legacy_not_resumable",
        "recoverable_partial_apply",
    }:
        return RECOVERY_OR_CONFIG
    if last.type == "approval.required" and last.payload.get("kind") == "recovery":
        return RECOVERY_OR_CONFIG
    return SUCCESS
