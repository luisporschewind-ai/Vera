from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.tools.registry import ToolRegistry


def make_app(tmp_path: Path) -> VeraTerminalApp:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir)
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake")


def make_block(index: int) -> TimelineBlock:
    return TimelineBlock(
        block_id=f"b{index}",
        run_id="run_1",
        kind=BlockKind.TOOL,
        title=f"tool-{index}",
        body="x" * 20,
        status=BlockStatus.SUCCEEDED,
        expanded=False,
    )


@pytest.mark.asyncio
async def test_new_output_does_not_steal_scroll_position(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(tuple(AppendBlock(block=make_block(i)) for i in range(40)))
        await pilot.pause()
        timeline.mark_user_scrolled()
        before = timeline.scroll_y
        app.append_output(
            EventEnvelope(
                event_id="e1",
                run_id="run_1",
                sequence=1,
                timestamp=datetime.now(UTC),
                type="tool.completed",
                payload={"name": "read_file", "ok": True, "result": "done"},
            )
        )
        await pilot.pause()
        assert timeline.scroll_y == before
        assert timeline.pending_update_count >= 1
        timeline.return_to_tail()
        assert timeline.follow_tail is True
        assert timeline.pending_update_count == 0


@pytest.mark.asyncio
async def test_timeline_widget_count_matches_blocks(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        blocks = [make_block(i) for i in range(50)]
        # One block with a huge body still mounts as one widget.
        blocks.append(
            TimelineBlock(
                block_id="huge",
                run_id="run_1",
                kind=BlockKind.TOOL,
                title="huge",
                body="\n".join(f"line-{i}" for i in range(10_000)),
                status=BlockStatus.SUCCEEDED,
                expanded=False,
            )
        )
        timeline.apply(tuple(AppendBlock(block=block) for block in blocks))
        await pilot.pause()
        assert timeline.widget_count() == len(blocks)
