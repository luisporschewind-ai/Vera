from datetime import UTC, datetime
from time import perf_counter

from vera.contracts.events import EventEnvelope
from vera.presentation.projector import TimelineProjector
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.terminal.performance import MAX_MOUNTED_BLOCKS, evictable_ids, is_pinned
from vera.terminal.widgets.blocks import TimelineBlockWidget


def test_pinned_blocks_survive_budget_and_collapsed_body_is_one_widget() -> None:
    blocks = []
    for index in range(500):
        blocks.append(
            TimelineBlock(
                block_id=f"tool_{index}",
                run_id="run_1",
                kind=BlockKind.TOOL,
                title="tool",
                body="line\n" * 20,
                status=BlockStatus.SUCCEEDED,
                expanded=False,
            )
        )
    pinned = (
        TimelineBlock(
            block_id="diff_1",
            run_id="run_1",
            kind=BlockKind.DIFF,
            title="Diff",
            body="--- a\n+++ b\n",
            expanded=True,
        ),
        TimelineBlock(
            block_id="approval_1",
            run_id="run_1",
            kind=BlockKind.APPROVAL,
            title="Approval",
            expanded=True,
        ),
        TimelineBlock(
            block_id="error_1",
            run_id="run_1",
            kind=BlockKind.ERROR,
            title="Error",
            status=BlockStatus.FAILED,
            expanded=True,
        ),
    )
    all_blocks = (*blocks, *pinned)
    victims = evictable_ids(all_blocks, limit=MAX_MOUNTED_BLOCKS)
    assert all(not item.startswith("diff_") for item in victims)
    assert "approval_1" not in victims
    assert "error_1" not in victims
    assert all(is_pinned(item) for item in pinned)
    widget = TimelineBlockWidget(
        TimelineBlock(
            block_id="log_1",
            run_id="run_1",
            kind=BlockKind.LOG,
            title="log",
            body="line\n" * 10_000,
            expanded=False,
        )
    )
    assert widget.collapsed is True
    projector = TimelineProjector(max_blocks=200)
    assert projector._max_blocks == 200


def test_appending_large_history_stays_within_phase6_budget() -> None:
    projector = TimelineProjector(max_blocks=MAX_MOUNTED_BLOCKS)
    started = perf_counter()
    for index in range(400):
        projector.apply(
            EventEnvelope(
                event_id=f"e{index}",
                run_id="run_1",
                sequence=index + 1,
                timestamp=datetime.now(UTC),
                type="tool.started",
                payload={"name": "read_file", "call_id": f"c{index}", "target": "a.py"},
            )
        )
    elapsed_ms = (perf_counter() - started) * 1000
    assert len(projector._blocks) <= MAX_MOUNTED_BLOCKS
    assert elapsed_ms < 2500
