from datetime import datetime
from pathlib import Path

from vera.session.models import (
    ConversationStats,
    GitStatus,
    PermissionStatus,
    ReasoningStatus,
    SessionStatus,
)
from vera.terminal.brand import select_brand_mark
from vera.terminal.widgets.welcome import VeraWelcome, brand_header_text


def sample_status(
    *,
    source: str = "new",
    dirty: bool = False,
    available: bool = True,
    persist: str = "saved",
) -> SessionStatus:
    return SessionStatus(
        version="0.1.0",
        model_profile="fake",
        model_name="fake-model",
        workspace=Path("/tmp/demo"),
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


def test_full_header_is_two_lines() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    text = brand_header_text(
        mark,
        sample_status(dirty=True),
        columns=80,
        rows=24,
        now=datetime(2026, 9, 16, 10, 24),
    )
    lines = text.splitlines()
    assert lines[0] == "VERA"
    assert len(lines) == 2
    assert "demo" in lines[1]
    assert "main*" in lines[1]
    assert "审批 manual" in lines[1]
    assert "10:24" in lines[1]


def test_ascii_full_size_keeps_two_header_lines() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=False, no_color=False)
    assert mark.mode == "ascii"
    text = brand_header_text(
        mark,
        sample_status(),
        columns=80,
        rows=24,
        now=datetime(2026, 9, 16, 10, 24),
    )
    assert text.splitlines()[0] == "VERA"
    assert len(text.splitlines()) == 2
    assert mark.lines[0].isascii()
    assert "\x1b" not in text


def test_compact_header_is_one_line() -> None:
    mark = select_brand_mark(columns=60, rows=16, unicode=True, no_color=False)
    text = brand_header_text(mark, sample_status(), columns=60, rows=16)
    assert "\n" not in text
    assert text.startswith("VERA")


def test_welcome_stays_hidden() -> None:
    widget = VeraWelcome()
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    widget.set_content(mark, sample_status(source="new"), columns=80)
    assert widget.display is False
    widget.set_content(mark, sample_status(source="resumed"), columns=80)
    assert widget.display is False


def test_header_carries_session_facts() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    text = brand_header_text(
        mark,
        sample_status(source="resumed", persist="unsaved", available=False),
        columns=80,
        rows=24,
        now=datetime(2026, 9, 16, 10, 24),
    )
    assert "VERA" in text.splitlines()[0]
    assert "已恢复" in text
    assert "未保存" in text
    assert "非 Git" in text
    assert "审批 manual" in text
