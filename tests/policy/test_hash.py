"""Policy model and hash stability tests."""

from __future__ import annotations

from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind
from vera.policy.snapshot import EffectivePolicySnapshot, policy_hash


def test_display_reason_does_not_change_policy_hash() -> None:
    snapshot = EffectivePolicySnapshot(
        workspace_identity="ws",
        user_allowed_command_prefixes=(("pytest",),),
    )
    engine = PolicyEngine(snapshot)
    first = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="pytest",
            argv=("pytest", "-q"),
        )
    )
    second = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="pytest",
            argv=("pytest", "-q"),
            metadata={"reason": "different display text"},
        )
    )
    assert first.policy_hash == second.policy_hash == policy_hash(snapshot)


def test_policy_hash_changes_when_effective_prefix_changes() -> None:
    first = EffectivePolicySnapshot(
        workspace_identity="ws",
        user_allowed_command_prefixes=(("pytest",),),
    )
    second = EffectivePolicySnapshot(
        workspace_identity="ws",
        user_allowed_command_prefixes=(("ruff",),),
    )
    assert policy_hash(first) != policy_hash(second)
