from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock


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
