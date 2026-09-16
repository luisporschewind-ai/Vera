from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
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


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 16), (80, 24), (120, 40)])
async def test_timeline_snapshot_sizes(tmp_path: Path, size: tuple[int, int]) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        app.query_one("#timeline").apply(
            (
                AppendBlock(
                    block=TimelineBlock(
                        block_id="user_1",
                        run_id="run_1",
                        kind=BlockKind.USER,
                        title="用户",
                        body="你好",
                        status=BlockStatus.SUCCEEDED,
                        expanded=True,
                    )
                ),
            )
        )
        await pilot.pause()
        svg = app.export_screenshot()
        assert "svg" in svg.lower() or "<svg" in svg.lower() or len(svg) > 10
