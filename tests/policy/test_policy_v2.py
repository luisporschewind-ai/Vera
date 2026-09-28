from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from vera.contracts.tool_actions import (
    ToolAction,
    ToolEffect,
    ToolRiskFacts,
    tool_action_input_hash,
)
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyDecisionKind, PolicyMode, RiskLevel
from vera.policy.permissions import (
    PermissionGrant,
    WorkspacePermissionSnapshot,
    classify_risk,
    decide_v2,
    permission_summary,
)
from vera.policy.snapshot import (
    EffectivePolicySnapshot,
    EffectivePolicySnapshotV2,
    protected_roots_hash,
)

_PROTECTED_ROOTS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    "*.p12",
    "*.pfx",
)
_PROTECTED_HASH = protected_roots_hash(_PROTECTED_ROOTS)


def _action(
    effect: ToolEffect,
    *,
    tool_name: str = "tool",
    arguments: dict[str, object] | None = None,
    risk_facts: ToolRiskFacts | None = None,
) -> ToolAction:
    normalized = arguments or {}
    effects = (effect,)
    facts = risk_facts or ToolRiskFacts(
        facts_complete=True,
        normalized_paths=("src/app.py",)
        if effect in {ToolEffect.WORKSPACE_READ, ToolEffect.WORKSPACE_WRITE}
        else (),
        argv=("pytest", "-q") if effect is ToolEffect.PROCESS_EXECUTE else (),
        cwd="." if effect is ToolEffect.PROCESS_EXECUTE else None,
        recoverable=effect is ToolEffect.WORKSPACE_WRITE,
    )
    return ToolAction(
        action_id="action_1",
        run_id="run_1",
        tool_name=tool_name,
        tool_version=2,
        effects=effects,
        workspace_identity="workspace_1",
        normalized_arguments=normalized,
        risk_facts=facts,
        input_hash=tool_action_input_hash(
            tool_name=tool_name,
            tool_version=2,
            workspace_identity="workspace_1",
            effects=effects,
            normalized_arguments=normalized,
            risk_facts=facts,
        ),
    )


def _snapshot(*, trusted: bool, grants: tuple[PermissionGrant, ...] = ()):
    return WorkspacePermissionSnapshot(
        workspace_identity="workspace_1",
        policy_major_version=2,
        trusted=trusted,
        protected_roots_hash=_PROTECTED_HASH,
        grants=grants,
    )


@pytest.mark.parametrize(
    ("effect", "trusted", "expected"),
    [
        (ToolEffect.WORKSPACE_READ, False, RiskLevel.LOW),
        (ToolEffect.WORKSPACE_WRITE, True, RiskLevel.LOW),
        (ToolEffect.WORKSPACE_WRITE, False, RiskLevel.MODERATE),
        (ToolEffect.PROCESS_EXECUTE, True, RiskLevel.MODERATE),
        (ToolEffect.NETWORK_ACCESS, True, RiskLevel.HIGH),
        (ToolEffect.EXTERNAL_SERVICE, True, RiskLevel.HIGH),
        (ToolEffect.SECRET_ACCESS, True, RiskLevel.FORBIDDEN),
    ],
)
def test_classify_risk_covers_effects_and_workspace_trust(
    effect: ToolEffect, trusted: bool, expected: RiskLevel
) -> None:
    assessment = classify_risk(_action(effect), _snapshot(trusted=trusted))
    assert assessment.level is expected
    assert assessment.reason_codes


@pytest.mark.parametrize("mode", list(PolicyMode))
def test_forbidden_never_relaxes_by_mode(mode: PolicyMode) -> None:
    decision = decide_v2(
        _action(ToolEffect.SECRET_ACCESS),
        _snapshot(trusted=True),
        mode=mode,
        goal_authorized=True,
    )
    assert decision.decision is PolicyDecisionKind.DENY
    assert decision.reason_code == "risk_forbidden"


@pytest.mark.parametrize(
    ("mode", "effect", "trusted", "goal_authorized", "expected"),
    [
        (PolicyMode.REVIEW, ToolEffect.WORKSPACE_READ, False, False, "allow"),
        (PolicyMode.REVIEW, ToolEffect.WORKSPACE_WRITE, True, True, "approval_required"),
        (PolicyMode.BALANCED, ToolEffect.WORKSPACE_WRITE, True, True, "allow"),
        (PolicyMode.BALANCED, ToolEffect.WORKSPACE_WRITE, True, False, "approval_required"),
        (PolicyMode.BALANCED, ToolEffect.WORKSPACE_WRITE, False, True, "approval_required"),
        (PolicyMode.BALANCED, ToolEffect.PROCESS_EXECUTE, True, True, "allow"),
        (PolicyMode.AUTONOMOUS, ToolEffect.PROCESS_EXECUTE, True, True, "allow"),
        (PolicyMode.AUTONOMOUS, ToolEffect.PROCESS_EXECUTE, True, False, "approval_required"),
        (PolicyMode.AUTONOMOUS, ToolEffect.NETWORK_ACCESS, True, True, "approval_required"),
    ],
)
def test_policy_v2_mode_trust_goal_matrix(
    mode: PolicyMode,
    effect: ToolEffect,
    trusted: bool,
    goal_authorized: bool,
    expected: str,
) -> None:
    decision = decide_v2(
        _action(effect),
        _snapshot(trusted=trusted),
        mode=mode,
        goal_authorized=goal_authorized,
    )
    assert decision.decision.value == expected


def test_matching_grant_is_structured_and_cannot_cross_arguments_or_run() -> None:
    grant = PermissionGrant(
        grant_id="grant_1",
        scope="run",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["pytest", "-q"]},
        run_id="run_1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    snapshot = _snapshot(trusted=True, grants=(grant,))

    allowed = decide_v2(
        _action(
            ToolEffect.PROCESS_EXECUTE,
            tool_name="bash",
            arguments={"argv": ["pytest", "-q"]},
        ),
        snapshot,
        mode=PolicyMode.REVIEW,
        goal_authorized=False,
    )
    changed_arguments = decide_v2(
        _action(
            ToolEffect.PROCESS_EXECUTE,
            tool_name="bash",
            arguments={"argv": ["pytest", "tests"]},
        ),
        snapshot,
        mode=PolicyMode.REVIEW,
        goal_authorized=False,
    )

    assert allowed.decision is PolicyDecisionKind.ALLOW
    assert allowed.reason_code == "permission_grant_matched"
    assert changed_arguments.decision is PolicyDecisionKind.APPROVAL_REQUIRED


def test_content_risk_can_only_tighten_v2_decision() -> None:
    decision = decide_v2(
        _action(ToolEffect.WORKSPACE_READ),
        _snapshot(trusted=True),
        mode=PolicyMode.BALANCED,
        goal_authorized=True,
        risk_labels=("instruction_override",),
        detector_disposition="warn",
    )
    assert decision.decision is PolicyDecisionKind.APPROVAL_REQUIRED
    assert decision.reason_code == "risk_tightened"


def test_v2_snapshot_defaults_balanced_without_breaking_v1_decoder() -> None:
    legacy = EffectivePolicySnapshot.model_validate({"workspace_identity": "workspace_1"})
    current = EffectivePolicySnapshotV2(workspace_identity="workspace_1")

    assert legacy.builtin_policy_version == 1
    assert not hasattr(legacy, "policy_mode")
    assert current.builtin_policy_version == 2
    assert current.policy_mode is PolicyMode.BALANCED


def test_policy_engine_remains_the_decision_entrypoint_for_tool_actions() -> None:
    engine = PolicyEngine(EffectivePolicySnapshotV2(workspace_identity="workspace_1"))
    decision = engine.decide_tool_action(
        _action(ToolEffect.WORKSPACE_WRITE),
        _snapshot(trusted=True),
        goal_authorized=True,
    )

    assert decision.decision is PolicyDecisionKind.ALLOW
    assert decision.policy_hash == engine.policy_hash


def test_public_permission_summary_excludes_private_rule_bodies() -> None:
    grant = PermissionGrant(
        grant_id="secret-grant-id",
        scope="workspace",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["private-command", "--token", "secret"]},
    )
    summary = permission_summary(
        _snapshot(trusted=True, grants=(grant,)),
        mode=PolicyMode.BALANCED,
    )
    dumped = summary.model_dump_json()

    assert set(type(summary).model_fields) == {
        "schema_version",
        "mode",
        "trusted",
        "rule_summaries",
        "snapshot_hash",
    }
    assert summary.rule_summaries == ("bash:process_execute:workspace",)
    assert "private-command" not in dumped
    assert "secret-grant-id" not in dumped


@pytest.mark.parametrize(
    "payload",
    [
        {"effects": ()},
        {"argument_constraints": {}},
        {"scope": "run", "run_id": None},
        {"scope": "workspace", "run_id": "run_1"},
        {"expires_at": datetime(2026, 9, 18)},
    ],
)
def test_permission_grants_reject_ambiguous_or_broad_scopes(payload: dict[str, object]) -> None:
    valid: dict[str, object] = {
        "grant_id": "grant_1",
        "scope": "workspace",
        "tool_name": "bash",
        "effects": (ToolEffect.PROCESS_EXECUTE,),
        "argument_constraints": {"argv": ["pytest", "-q"]},
    }
    valid.update(payload)
    with pytest.raises(ValueError):
        PermissionGrant.model_validate(valid)


def test_once_grant_matches_only_the_exact_action_input_hash() -> None:
    action = _action(
        ToolEffect.PROCESS_EXECUTE,
        tool_name="bash",
        arguments={"argv": ["pytest", "-q"]},
    )
    grant = PermissionGrant(
        grant_id="grant_1",
        scope="once",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["pytest", "-q"]},
        run_id="run_1",
        action_input_hash=action.input_hash,
        action_id=action.action_id,
    )
    snapshot = _snapshot(trusted=True, grants=(grant,))

    exact = decide_v2(
        action,
        snapshot,
        mode=PolicyMode.REVIEW,
        goal_authorized=False,
    )
    different = decide_v2(
        _action(
            ToolEffect.PROCESS_EXECUTE,
            tool_name="bash",
            arguments={"argv": ["pytest", "tests"]},
        ),
        snapshot,
        mode=PolicyMode.REVIEW,
        goal_authorized=False,
    )
    replay_with_new_action_id = decide_v2(
        action.model_copy(update={"action_id": "action_2"}),
        snapshot,
        mode=PolicyMode.REVIEW,
        goal_authorized=False,
    )

    assert exact.decision is PolicyDecisionKind.ALLOW
    assert different.decision is PolicyDecisionKind.APPROVAL_REQUIRED
    assert replay_with_new_action_id.decision is PolicyDecisionKind.APPROVAL_REQUIRED


@pytest.mark.parametrize("effect", [ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE])
def test_incomplete_risk_facts_never_auto_allow_side_effects(effect: ToolEffect) -> None:
    decision = decide_v2(
        _action(effect, risk_facts=ToolRiskFacts()),
        _snapshot(trusted=True),
        mode=PolicyMode.AUTONOMOUS,
        goal_authorized=True,
    )
    assert decision.decision is PolicyDecisionKind.APPROVAL_REQUIRED
    assert decision.reason_code == "high_risk_approval_required"


def test_incomplete_read_facts_do_not_auto_allow_hidden_sensitive_paths() -> None:
    decision = decide_v2(
        _action(
            ToolEffect.WORKSPACE_READ,
            arguments={"path": ".env"},
            risk_facts=ToolRiskFacts(),
        ),
        _snapshot(trusted=True),
        mode=PolicyMode.BALANCED,
        goal_authorized=True,
    )
    assert decision.decision is PolicyDecisionKind.APPROVAL_REQUIRED


def test_engine_fails_closed_on_policy_workspace_and_protected_root_mismatch() -> None:
    action = _action(ToolEffect.WORKSPACE_WRITE)
    v1_engine = PolicyEngine(EffectivePolicySnapshot(workspace_identity="workspace_1"))
    other_workspace = PolicyEngine(EffectivePolicySnapshotV2(workspace_identity="workspace_other"))
    current = PolicyEngine(EffectivePolicySnapshotV2(workspace_identity="workspace_1"))

    assert (
        v1_engine.decide_tool_action(action, _snapshot(trusted=True), goal_authorized=True).decision
        is PolicyDecisionKind.DENY
    )
    assert (
        other_workspace.decide_tool_action(
            action, _snapshot(trusted=True), goal_authorized=True
        ).decision
        is PolicyDecisionKind.DENY
    )
    assert (
        current.decide_tool_action(
            action,
            _snapshot(trusted=True).model_copy(update={"policy_major_version": 99}),
            goal_authorized=True,
        ).decision
        is PolicyDecisionKind.DENY
    )
    assert (
        current.decide_tool_action(
            action,
            _snapshot(trusted=True).model_copy(update={"protected_roots_hash": "f" * 64}),
            goal_authorized=True,
        ).decision
        is PolicyDecisionKind.DENY
    )


def test_engine_applies_project_denies_before_v2_auto_allow() -> None:
    engine = PolicyEngine(
        EffectivePolicySnapshotV2(
            workspace_identity="workspace_1",
            project_denied_tools=("edit",),
            project_denied_path_globs=("generated/*",),
        )
    )
    denied_tool = _action(ToolEffect.WORKSPACE_WRITE, tool_name="edit")
    denied_path = _action(
        ToolEffect.WORKSPACE_WRITE,
        tool_name="write",
        risk_facts=ToolRiskFacts(
            facts_complete=True,
            normalized_paths=("generated/output.py",),
            recoverable=True,
        ),
    )

    assert (
        engine.decide_tool_action(
            denied_tool, _snapshot(trusted=True), goal_authorized=True
        ).reason_code
        == "project_tool_denied"
    )
    assert (
        engine.decide_tool_action(
            denied_path, _snapshot(trusted=True), goal_authorized=True
        ).reason_code
        == "sensitive_path_forbidden"
    )


def test_workspace_grant_cannot_downgrade_high_risk_external_effect() -> None:
    action = _action(
        ToolEffect.NETWORK_ACCESS,
        tool_name="publish",
        arguments={"target": "example.invalid"},
    )
    grant = PermissionGrant(
        grant_id="grant_1",
        scope="workspace",
        tool_name="publish",
        effects=(ToolEffect.NETWORK_ACCESS,),
        argument_constraints=action.normalized_arguments,
    )
    decision = decide_v2(
        action,
        _snapshot(trusted=True, grants=(grant,)),
        mode=PolicyMode.AUTONOMOUS,
        goal_authorized=True,
    )
    assert decision.decision is PolicyDecisionKind.APPROVAL_REQUIRED


def test_policy_engine_consumes_an_once_grant_after_its_first_allow() -> None:
    action = _action(
        ToolEffect.PROCESS_EXECUTE, tool_name="bash", arguments={"argv": ["pytest", "-q"]}
    )
    grant = PermissionGrant(
        grant_id="grant_1",
        scope="once",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["pytest", "-q"]},
        run_id="run_1",
        action_id=action.action_id,
        action_input_hash=action.input_hash,
    )
    engine = PolicyEngine(EffectivePolicySnapshotV2(workspace_identity="workspace_1"))
    permissions = _snapshot(trusted=True, grants=(grant,))

    first = engine.decide_tool_action(action, permissions, goal_authorized=False)
    second = engine.decide_tool_action(action, permissions, goal_authorized=False)

    assert first.decision is PolicyDecisionKind.ALLOW
    assert second.decision is PolicyDecisionKind.APPROVAL_REQUIRED


def test_policy_engine_consumes_the_exact_once_grant_that_matched() -> None:
    action = _action(
        ToolEffect.PROCESS_EXECUTE, tool_name="bash", arguments={"argv": ["pytest", "-q"]}
    )
    nonmatching = PermissionGrant(
        grant_id="grant_wrong",
        scope="once",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["pytest", "other"]},
        run_id="run_1",
        action_id=action.action_id,
        action_input_hash=action.input_hash,
    )
    matching = nonmatching.model_copy(
        update={"grant_id": "grant_right", "argument_constraints": action.normalized_arguments}
    )
    engine = PolicyEngine(EffectivePolicySnapshotV2(workspace_identity="workspace_1"))
    permissions = _snapshot(trusted=True, grants=(nonmatching, matching))

    first = engine.decide_tool_action(action, permissions, goal_authorized=False)
    second = engine.decide_tool_action(action, permissions, goal_authorized=False)

    assert first.decision is PolicyDecisionKind.ALLOW
    assert second.decision is PolicyDecisionKind.APPROVAL_REQUIRED
