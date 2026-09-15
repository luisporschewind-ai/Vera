from datetime import UTC, datetime

from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock, format_block_clock


def test_timeline_block_is_frozen() -> None:
    block = TimelineBlock(
        block_id="b1",
        run_id="run_1",
        kind=BlockKind.USER,
        title="user",
        body="hi",
        status=BlockStatus.SUCCEEDED,
        expanded=True,
    )
    assert block.kind is BlockKind.USER
    try:
        block.title = "x"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("expected frozen model")


def test_format_block_clock_is_local_12h_ampm() -> None:
    assert format_block_clock(None) == ""
    clock = format_block_clock(datetime(2026, 9, 15, 8, 4, tzinfo=UTC))
    assert clock.endswith(" AM") or clock.endswith(" PM")
    assert ":" in clock
    hour, rest = clock.split(":", 1)
    assert hour.isdigit() and 1 <= int(hour) <= 12
    naive = format_block_clock(datetime(2026, 9, 15, 8, 4))
    assert naive == clock
