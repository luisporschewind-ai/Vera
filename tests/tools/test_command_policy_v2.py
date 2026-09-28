import pytest

from vera.policy.models import RiskLevel
from vera.tools.command_policy import CommandClassifier


@pytest.mark.parametrize(
    ("argv", "risk", "reason"),
    [
        (("rg", "TODO", "."), RiskLevel.LOW, ""),
        (("pytest", "-q"), RiskLevel.LOW, ""),
        (("ruff", "check", "."), RiskLevel.LOW, ""),
        (("git", "commit", "-m", "x"), RiskLevel.HIGH, "workspace_write"),
        (("pip", "install", "requests"), RiskLevel.HIGH, "package_install"),
        (("make", "build"), RiskLevel.HIGH, "build_or_verification"),
        (("prettier", "--write", "src"), RiskLevel.HIGH, "workspace_write"),
        (("python", "-m", "http.server"), RiskLevel.HIGH, "background_service"),
        (("curl", "https://example.test"), RiskLevel.HIGH, "network_access"),
        (("bash", "-c", "echo x"), RiskLevel.FORBIDDEN, "shell_forbidden"),
        (("sudo", "id"), RiskLevel.FORBIDDEN, "privilege_forbidden"),
        (("rm", "-rf", "x"), RiskLevel.FORBIDDEN, "destructive_forbidden"),
    ],
)
def test_command_classifier_matrix(argv, risk, reason) -> None:
    classification = CommandClassifier().classify(argv)
    assert classification.risk_level is risk
    if reason:
        assert reason in classification.reason_codes


def test_command_classifier_preserves_argv_as_data() -> None:
    classification = CommandClassifier().classify(("printf", "a | b $(echo no)"))
    assert classification.executable == "printf"
    assert classification.risk_level is RiskLevel.MODERATE
