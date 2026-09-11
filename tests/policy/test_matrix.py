"""Command policy decision matrix."""

from __future__ import annotations

import pytest

from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind
from vera.policy.snapshot import EffectivePolicySnapshot


def engine_with_prefixes(prefixes: tuple[tuple[str, ...], ...]) -> PolicyEngine:
    return PolicyEngine(
        EffectivePolicySnapshot(
            workspace_identity="ws",
            user_allowed_command_prefixes=prefixes,
        )
    )


def command_action(argv: tuple[str, ...]) -> PolicyAction:
    return PolicyAction(
        kind=PolicyActionKind.COMMAND_EXECUTE,
        workspace_identity="ws",
        resource=argv[0] if argv else "",
        argv=argv,
    )


@pytest.mark.parametrize(
    ("argv", "prefixes", "expected", "reason_code"),
    [
        (("sudo", "pytest"), (("sudo",),), "deny", "privilege_forbidden"),
        (("zsh", "-lc", "pytest"), (("zsh",),), "deny", "shell_forbidden"),
        (("rm", "-rf", "build"), (("rm",),), "deny", "deletion_forbidden"),
        (("pytest", "-q"), (("pytest",),), "allow", "user_prefix_allowed"),
        (("git", "diff", "--check"), (), "allow", "builtin_safe_command"),
        (("xcodebuild", "test"), (), "approval_required", "command_not_preapproved"),
    ],
)
def test_command_policy_precedence(argv, prefixes, expected, reason_code) -> None:
    engine = engine_with_prefixes(prefixes)
    decision = engine.decide(command_action(argv))
    assert decision.decision.value == expected
    assert decision.reason_code == reason_code


def test_tool_and_changeset_actions_cover_engine_branches() -> None:
    engine = PolicyEngine(
        EffectivePolicySnapshot(
            workspace_identity="ws",
            project_denied_tools=("search_text",),
        )
    )
    deny_tool = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.TOOL_EXECUTE,
            workspace_identity="ws",
            resource="search_text",
        )
    )
    assert deny_tool.decision.value == "deny"
    allow_tool = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.TOOL_EXECUTE,
            workspace_identity="ws",
            resource="read_file",
        )
    )
    assert allow_tool.decision.value == "allow"
    changeset = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.CHANGESET_APPLY,
            workspace_identity="ws",
            resource="cs_1",
        )
    )
    assert changeset.decision.value == "approval_required"
