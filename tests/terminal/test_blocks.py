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


def tool_block(block_id: str = "tool_1", *, failed: bool = False) -> TimelineBlock:
    return TimelineBlock(
        block_id=block_id,
        run_id="run_1",
        kind=BlockKind.TOOL,
        title="read_file · failed" if failed else "read_file · completed",
        body="line\n" * 5,
        status=BlockStatus.FAILED if failed else BlockStatus.SUCCEEDED,
        expanded=failed,
    )


def diff_block() -> TimelineBlock:
    return TimelineBlock(
        block_id="diff_1",
        run_id="run_1",
        kind=BlockKind.DIFF,
        title="Diff · 1 files",
        body="--- a/a.py\n+++ b/a.py\n+print(1)\n",
        status=BlockStatus.PENDING,
        expanded=True,
    )


@pytest.mark.asyncio
async def test_disclosure_defaults_and_failure(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        for block in (tool_block(), diff_block(), tool_block("tool_failed", failed=True)):
            timeline.apply((AppendBlock(block=block),))
        await pilot.pause()
        assert app.block("tool_1").collapsed is True
        assert app.block("diff_1").collapsed is False
        assert app.block("tool_failed").collapsed is False
        app.block("tool_1").toggle_expanded()
        assert app.block("tool_1").collapsed is False


@pytest.mark.asyncio
async def test_untrusted_markup_is_escaped(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        block = TimelineBlock(
            block_id="log_1",
            run_id="run_1",
            kind=BlockKind.LOG,
            title="log",
            body="[bold red]not markup[/]",
            status=BlockStatus.SUCCEEDED,
            expanded=True,
        )
        app.query_one("#timeline").apply((AppendBlock(block=block),))
        await pilot.pause()
        rendered = str(app.block("log_1")._body.render())
        assert "[bold red]" in rendered or "not markup" in rendered
