from pathlib import Path

import pytest

from vera.cli_presenter import HumanPresenter
from vera.contracts.verification import VerificationCommand
from vera.policy.engine import PolicyEngine
from vera.policy.models import PolicyAction, PolicyActionKind
from vera.tools.command_policy import CommandDecisionKind, CommandPolicy
from vera.verification.artifacts import VerificationArtifactPlanner


@pytest.mark.parametrize(
    "argv",
    [
        ("sh", "-c", "echo x"),
        ("sudo", "true"),
        ("rm", "-rf", "."),
        ("env", "zsh", "-c", "echo x"),
        ("/bin/bash", "-lc", "id"),
    ],
)
def test_forbidden_commands_never_request_approval(argv: tuple[str, ...]) -> None:
    decision = CommandPolicy().classify(VerificationCommand(argv=argv, cwd="."))
    assert decision.kind is CommandDecisionKind.FORBIDDEN


def test_exact_user_prefix_is_policy_allowed() -> None:
    policy = CommandPolicy(user_allowed_prefixes=(("python", "-m", "pytest"),))
    command = VerificationCommand(argv=("python", "-m", "pytest", "-q"), cwd=".")
    assert policy.classify(command).kind is CommandDecisionKind.ALLOWED


def test_safe_builtins_and_unknown_commands() -> None:
    policy = CommandPolicy()
    assert (
        policy.classify(VerificationCommand(argv=("git", "diff", "--check"))).kind
        is CommandDecisionKind.ALLOWED
    )
    assert (
        policy.classify(VerificationCommand(argv=("ruff", "check", "."))).kind
        is CommandDecisionKind.APPROVAL_REQUIRED
    )


def test_final_planned_command_is_what_policy_classifies(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    planner = VerificationArtifactPlanner(prefix=tmp_path / "vera-verification")
    original = VerificationCommand(argv=("ruff", "check", "."), cwd=".")
    planned = planner.plan(
        original,
        workspace_root=workspace,
        installation_id="install-1",
        run_id="run_1",
        index=0,
    )
    policy = CommandPolicy()
    original_kind = policy.classify(original).kind
    planned_kind = policy.classify(planned).kind
    assert original_kind is CommandDecisionKind.APPROVAL_REQUIRED
    assert planned_kind is CommandDecisionKind.APPROVAL_REQUIRED
    assert original.argv != planned.argv
    assert "--no-cache" in planned.argv


def test_command_policy_matches_engine_and_presenter_cannot_override() -> None:
    policy = CommandPolicy()
    command = VerificationCommand(argv=("rm", "-rf", "."), cwd=".")
    classified = policy.classify(command)
    engine_decision = PolicyEngine(policy.engine.snapshot).decide(
        PolicyAction(
            kind=PolicyActionKind.COMMAND_EXECUTE,
            workspace_identity=policy.workspace_identity,
            resource=command.argv[0],
            argv=command.argv,
            metadata={"cwd": command.cwd},
        )
    )
    assert classified.reason_code == engine_decision.reason_code
    assert classified.policy_hash == engine_decision.policy_hash
    assert not hasattr(HumanPresenter, "classify")
    assert not hasattr(HumanPresenter, "decide")
