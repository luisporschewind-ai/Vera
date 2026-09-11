from pathlib import Path

from vera.cli_session_presenter import SessionPresenter
from vera.session.models import ConversationStats, GitStatus, PermissionStatus, SessionStatus


def sample_status(*, dirty: bool = True, available: bool = True) -> SessionStatus:
    return SessionStatus(
        version="0.1.0",
        model_profile="deepseek",
        model_name="deepseek-flash",
        workspace=Path("/tmp/project").resolve(),
        git=GitStatus(
            available=available,
            branch="main" if available else None,
            dirty=dirty if available else None,
        ),
        context=ConversationStats(
            session_id="session-1",
            message_count=2,
            context_bytes=20,
            max_bytes=200_000,
            warning=False,
            compaction_count=1,
        ),
        permissions=PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow/deny/approval-required",
            user_allowed_prefixes=(("python", "-m", "pytest"),),
            execution_boundary="current user",
            os_sandbox=False,
        ),
    )


def test_session_presenter_renders_status_panel_without_secrets() -> None:
    output: list[str] = []
    presenter = SessionPresenter(output.append)

    presenter.write_status(sample_status())

    text = "\n".join(output)
    assert "Vera 0.1.0" in text
    assert "deepseek / deepseek-flash" in text
    assert str(Path("/tmp/project").resolve()) in text
    assert "main · dirty" in text
    assert "session-1" in text
    assert "2 messages" in text
    assert "manual" in text
    assert "no OS sandbox" in text
    assert "must-not-render" not in text
    assert "api" not in text.lower()
    assert "sk-" not in text


def test_session_presenter_context_hides_message_bodies() -> None:
    output: list[str] = []
    presenter = SessionPresenter(output.append)
    stats = ConversationStats(
        session_id="session-1",
        message_count=2,
        context_bytes=42,
        max_bytes=200_000,
        warning=True,
        compaction_count=0,
    )

    presenter.write_context(stats)

    text = "\n".join(output)
    assert "42/200000" in text
    assert "must-not-render" not in text
    assert "2 messages" in text


def test_session_presenter_permissions_lists_effective_prefixes() -> None:
    output: list[str] = []
    presenter = SessionPresenter(output.append)
    status = PermissionStatus(
        approval_mode="manual",
        changeset_approval="required",
        command_policy="allow/deny/approval-required",
        user_allowed_prefixes=(("python", "-m", "pytest"),),
        execution_boundary="current user",
        os_sandbox=False,
    )

    presenter.write_permissions(status)

    text = "\n".join(output)
    assert "Change Set" in text or "changeset" in text.lower() or "required" in text
    assert "python -m pytest" in text
    assert "current user" in text
    assert "no OS sandbox" in text
