import pytest

from vera.contracts.verification import VerificationCommand
from vera.tools.command_policy import CommandDecisionKind, CommandPolicy


@pytest.mark.parametrize(
    "argv",
    [("sh", "-c", "echo x"), ("sudo", "true"), ("rm", "-rf", ".")],
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
