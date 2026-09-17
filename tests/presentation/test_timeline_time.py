from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.presentation.timeline_time import (
    format_timeline_clock,
    should_omit_timeline_block,
)


def test_unknown_time_is_omitted() -> None:
    assert format_timeline_clock(None) == ""


def test_naive_datetime_is_treated_as_utc() -> None:
    aware = format_timeline_clock(datetime(2026, 9, 15, 8, 4, tzinfo=UTC), tz=UTC)
    naive = format_timeline_clock(datetime(2026, 9, 15, 8, 4), tz=UTC)
    assert aware == "8:04 AM"
    assert naive == aware


def test_utc_crossing_local_day() -> None:
    clock = format_timeline_clock(
        datetime(2026, 9, 15, 23, 30, tzinfo=UTC),
        tz=ZoneInfo("Asia/Shanghai"),
    )
    assert clock == "7:30 AM"


def test_dst_spring_forward_keeps_original_instant() -> None:
    before = format_timeline_clock(
        datetime(2026, 3, 8, 6, 59, tzinfo=UTC),
        tz=ZoneInfo("America/New_York"),
    )
    after = format_timeline_clock(
        datetime(2026, 3, 8, 7, 0, tzinfo=UTC),
        tz=ZoneInfo("America/New_York"),
    )
    assert before == "1:59 AM"
    assert after == "3:00 AM"


def test_afternoon_is_pm_without_leading_zero() -> None:
    clock = format_timeline_clock(
        datetime(2026, 9, 15, 13, 21, tzinfo=UTC),
        tz=UTC,
    )
    assert clock == "1:21 PM"


def test_empty_and_decorative_blocks_are_omitted() -> None:
    assert should_omit_timeline_block(BlockKind.USER, "用户", "   ") is True
    assert should_omit_timeline_block(BlockKind.ASSISTANT, "助手", "") is True
    assert should_omit_timeline_block(BlockKind.STATUS, "·", "·") is True
    assert should_omit_timeline_block(BlockKind.ERROR, "Error", "") is False


def test_duplicate_status_is_omitted() -> None:
    previous = TimelineBlock(
        block_id="s1",
        run_id="run_1",
        kind=BlockKind.STATUS,
        title="会话状态",
        body="ok",
        status=BlockStatus.SUCCEEDED,
    )
    assert should_omit_timeline_block(BlockKind.STATUS, "会话状态", "ok", previous=previous)
    assert not should_omit_timeline_block(
        BlockKind.STATUS, "会话状态", "changed", previous=previous
    )
