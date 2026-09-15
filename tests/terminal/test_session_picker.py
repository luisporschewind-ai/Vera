from datetime import UTC, datetime

from vera.persistence.session_store import ConversationSessionSummary
from vera.terminal.widgets.session_picker import format_picker_rows


def sample(recoverable: bool = True, title: str = "短标题") -> ConversationSessionSummary:
    return ConversationSessionSummary(
        session_id="session_abcdefghijklmnop",
        title=title,
        updated_at=datetime(2026, 9, 16, tzinfo=UTC),
        message_count=2,
        latest_run_id="run_1",
        latest_run_state="completed",
        recoverable=recoverable,
    )


def test_narrow_size_uses_short_id_and_truncated_title() -> None:
    rows = format_picker_rows(
        (sample(title="这是一个需要被截断的非常长的会话标题内容"),),
        columns=60,
        rows=16,
    )
    assert rows[0].startswith("1. session_")
    assert "session_abcdefghijklmnop" not in rows[0]
    assert "…" in rows[0]


def test_damaged_sessions_are_marked() -> None:
    rows = format_picker_rows((sample(recoverable=False),), columns=120, rows=40)
    assert "[损坏]" in rows[0]
    assert "session_abcdefghijklmnop" in rows[0]
