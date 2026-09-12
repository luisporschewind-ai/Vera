from vera.content.detector import DetectionDisposition
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind, PolicyDecision, PolicyDecisionKind
from vera.policy.snapshot import EffectivePolicySnapshot
from vera.policy.tighten import tighten_policy_decision


def _engine() -> PolicyEngine:
    return PolicyEngine(
        EffectivePolicySnapshot(
            workspace_identity="ws",
            user_allowed_command_prefixes=(("pytest",),),
            protected_path_globs=("**/.env", ".env"),
        )
    )


def _decision(kind: PolicyDecisionKind) -> PolicyDecision:
    return PolicyDecision(
        decision=kind,
        reason_code="base",
        reason="base",
        matched_rule="base",
        policy_hash="p" * 64,
    )


def test_tighten_matrix_never_relaxes_and_unknown_is_stricter() -> None:
    deny = _decision(PolicyDecisionKind.DENY)
    required = _decision(PolicyDecisionKind.APPROVAL_REQUIRED)
    allow = _decision(PolicyDecisionKind.ALLOW)
    assert tighten_policy_decision(deny, (), "clear").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(deny, ("instruction_override",), "warn").decision is (
        PolicyDecisionKind.DENY
    )
    assert tighten_policy_decision(deny, (), "block").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(required, (), "clear").decision is (
        PolicyDecisionKind.APPROVAL_REQUIRED
    )
    assert tighten_policy_decision(required, ("instruction_override",), "warn").decision is (
        PolicyDecisionKind.APPROVAL_REQUIRED
    )
    assert tighten_policy_decision(required, (), "quarantine").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(required, (), "block").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(required, (), "unavailable").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(allow, (), "clear").decision is PolicyDecisionKind.ALLOW
    assert tighten_policy_decision(allow, ("instruction_override",), "warn").decision is (
        PolicyDecisionKind.APPROVAL_REQUIRED
    )
    assert tighten_policy_decision(allow, ("not_a_real_label",), "clear").decision is (
        PolicyDecisionKind.APPROVAL_REQUIRED
    )
    assert tighten_policy_decision(allow, (), "quarantine").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(allow, (), "block").decision is PolicyDecisionKind.DENY
    assert tighten_policy_decision(allow, (), "unavailable").decision is PolicyDecisionKind.DENY
    unknown = tighten_policy_decision(allow, (), "not-a-disposition")
    assert unknown.decision is PolicyDecisionKind.DENY
    assert unknown.policy_hash == allow.policy_hash


def test_hard_denies_and_safe_allows_are_not_relaxed() -> None:
    engine = _engine()
    rm = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="rm",
            argv=("rm", "-rf", "."),
            metadata={"cwd": ".", "detector_disposition": "clear", "risk_labels": []},
        )
    )
    assert rm.decision is PolicyDecisionKind.DENY
    secret = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.PATH_READ,
            workspace_identity="ws",
            resource=".env",
            metadata={"detector_disposition": DetectionDisposition.CLEAR.value},
        )
    )
    assert secret.decision is PolicyDecisionKind.DENY
    git = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="git",
            argv=("git", "status", "--short"),
            metadata={
                "cwd": ".",
                "detector_disposition": "warn",
                "risk_labels": ["instruction_override"],
            },
        )
    )
    assert git.decision is PolicyDecisionKind.APPROVAL_REQUIRED
    assert git.reason_code == "risk_tightened"
    pytest_cmd = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="pytest",
            argv=("pytest", "-q"),
            metadata={
                "cwd": ".",
                "detector_disposition": "warn",
                "risk_labels": ["instruction_override"],
            },
        )
    )
    assert pytest_cmd.decision is PolicyDecisionKind.APPROVAL_REQUIRED
    clean_git = engine.decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity="ws",
            resource="git",
            argv=("git", "status", "--short"),
            metadata={"cwd": "."},
        )
    )
    assert clean_git.decision is PolicyDecisionKind.ALLOW
    assert clean_git.policy_hash == engine.policy_hash
