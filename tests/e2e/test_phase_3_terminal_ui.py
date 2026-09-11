from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.tools.registry import ToolRegistry


def make_app(tmp_path: Path, turns: list[ModelTurn] | None = None) -> VeraTerminalApp:
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
    runtime = VeraRuntime(FakeModelAdapter(turns or []), ToolRegistry(), state_dir)
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake", animations=False)


@pytest.mark.asyncio
async def test_safe_editing_tui_story_shell(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(
                    block=TimelineBlock(
                        block_id="diff_1",
                        run_id="run_1",
                        kind=BlockKind.DIFF,
                        title="Diff · 1 files",
                        body="--- a\n+++ b\n+x\n",
                        status=BlockStatus.PENDING,
                        expanded=True,
                    )
                ),
                AppendBlock(
                    block=TimelineBlock(
                        block_id="approval_1",
                        run_id="run_1",
                        kind=BlockKind.APPROVAL,
                        title="Approval required · changeset · low",
                        body="review",
                        status=BlockStatus.PENDING,
                        expanded=True,
                        ref_id="approval_1",
                    )
                ),
                AppendBlock(
                    block=TimelineBlock(
                        block_id="tool_1",
                        run_id="run_1",
                        kind=BlockKind.TOOL,
                        title="read_file · completed",
                        body="ok",
                        status=BlockStatus.SUCCEEDED,
                        expanded=False,
                    )
                ),
            )
        )
        await pilot.pause()
        assert app.block("diff_1").collapsed is False
        from vera.terminal.widgets.approval import ApprovalBlockWidget

        approval = app.block("approval_1")
        assert isinstance(approval, ApprovalBlockWidget)
        assert approval.focused_decision == "cancel"
        assert app.block("tool_1").collapsed is True
