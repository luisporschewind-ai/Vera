from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock, FocusBlock, UpdateBlock
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


@pytest.mark.asyncio
async def test_timeline_keys_and_focus_and_update(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        block = TimelineBlock(
            block_id="a1",
            run_id="run_1",
            kind=BlockKind.APPROVAL,
            title="Approval",
            body="please",
            status=BlockStatus.PENDING,
            expanded=True,
        )
        timeline.apply((AppendBlock(block=block), FocusBlock(block_id="a1")))
        await pilot.pause()
        timeline.apply(
            (
                UpdateBlock(
                    block=block.model_copy(update={"body": "updated body", "title": "Approval 2"})
                ),
            )
        )
        await pilot.pause()
        assert "updated body" in str(app.block("a1")._body.render())
        timeline.mark_user_scrolled()
        assert timeline.follow_tail is False
        timeline.on_key(type("E", (), {"key": "end", "stop": lambda self=None: None})())
        assert timeline.follow_tail is True
        await pilot.press("pageup")
        await pilot.pause()


@pytest.mark.asyncio
async def test_empty_diff_and_apply_block(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        empty_diff = TimelineBlock(
            block_id="d1",
            run_id="run_1",
            kind=BlockKind.DIFF,
            title="Diff",
            body="",
            status=BlockStatus.PENDING,
            expanded=True,
        )
        timeline.apply((AppendBlock(block=empty_diff),))
        await pilot.pause()
        app.block("d1").apply_block(
            empty_diff.model_copy(update={"body": "--- a\n+++ b\n+x\n", "expanded": False})
        )
        assert app.block("d1").collapsed is True
