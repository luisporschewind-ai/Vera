from pathlib import Path

from vera.session.models import (
    ConversationStats,
    GitStatus,
    PermissionStatus,
    ReasoningStatus,
    SessionStatus,
)
from vera.terminal.brand import select_brand_mark
from vera.terminal.widgets.welcome import (
    VeraWelcome,
    brand_header_text,
    format_workspace_path,
)


def sample_status(
    *,
    source: str = "new",
    dirty: bool = False,
    available: bool = True,
    persist: str = "saved",
    workspace: Path | None = None,
) -> SessionStatus:
    return SessionStatus(
        version="0.1.0",
        model_profile="fake",
        model_name="fake-model",
        workspace=workspace or Path("/tmp/demo"),
        git=GitStatus(
            available=available,
            branch="main" if available else None,
            dirty=dirty if available else None,
        ),
        context=ConversationStats(
            session_id="s1",
            message_count=0,
            context_bytes=0,
            max_bytes=100,
            warning=False,
            compaction_count=0,
            source=source,  # type: ignore[arg-type]
            persistent_state=persist,  # type: ignore[arg-type]
        ),
        permissions=PermissionStatus(
            approval_mode="manual",
            changeset_approval="required",
            command_policy="allow",
            user_allowed_prefixes=(),
            execution_boundary="current user",
            os_sandbox=False,
        ),
        reasoning=ReasoningStatus(mode="unavailable"),
    )


def test_welcome_card_is_three_lines() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    text = brand_header_text(mark, sample_status(dirty=True), columns=80, rows=24)
    lines = text.splitlines()
    assert len(lines) == 3
    assert "Vera  0.1.0" in lines[0]
    assert "demo" in lines[1]
    assert "fake-model" in lines[2]
    assert "推理 不可用" in lines[2]
    assert "新会话" not in text
    assert "审批" not in text
    assert "10:24" not in text


def test_ascii_welcome_is_three_ascii_lines() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=False, no_color=False)
    assert mark.mode == "ascii"
    text = brand_header_text(mark, sample_status(), columns=80, rows=24)
    assert len(text.splitlines()) == 3
    assert mark.lines[0].isascii()
    assert "\x1b" not in text


def test_shrunk_header_keeps_vera_next_to_path() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False, expanded=False)
    text = brand_header_text(
        mark, sample_status(workspace=Path("/tmp/demo")), columns=80, expanded=False
    )
    assert text == "VERA  /tmp/demo"
    assert "\n" not in text


def test_home_workspace_uses_tilde() -> None:
    path = Path.home() / "Desktop" / "VeraTestDemo"
    assert format_workspace_path(path) == "~/Desktop/VeraTestDemo"


def test_welcome_stays_hidden() -> None:
    widget = VeraWelcome()
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    widget.set_content(mark, sample_status(source="new"), columns=80)
    assert widget.display is False
    widget.set_content(mark, sample_status(source="resumed"), columns=80)
    assert widget.display is False


def test_welcome_card_omits_session_and_git_labels() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    text = brand_header_text(
        mark,
        sample_status(source="resumed", persist="unsaved", available=False),
        columns=80,
        rows=24,
    )
    assert "Vera  0.1.0" in text
    assert "已恢复" not in text
    assert "未保存" not in text
    assert "非 Git" not in text
    assert "审批" not in text
