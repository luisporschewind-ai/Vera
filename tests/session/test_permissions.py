from vera.session.permissions import permission_status
from vera.tools.command_policy import CommandPolicy


def test_permission_status_exposes_effective_policy_only() -> None:
    policy = CommandPolicy(user_allowed_prefixes=(("python", "-m", "pytest"),))

    status = permission_status(policy)

    assert status.approval_mode == "manual"
    assert status.changeset_approval == "required"
    assert status.command_policy == "allow/deny/approval-required"
    assert status.user_allowed_prefixes == (("python", "-m", "pytest"),)
    assert status.execution_boundary == "current user"
    assert status.os_sandbox is False
    serialized = status.model_dump_json().lower()
    assert "api" not in serialized
    assert "key" not in serialized
    assert "base_url" not in serialized


def test_permission_status_defaults_have_empty_prefixes() -> None:
    status = permission_status(CommandPolicy())
    assert status.user_allowed_prefixes == ()
