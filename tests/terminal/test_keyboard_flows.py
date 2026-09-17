from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.runtime.engine import VeraRuntime
from vera.session.actions import CancelActiveRun
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.approval import ApprovalBlockWidget
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
    return VeraTerminalApp(controller, workspace, "fake", animations=False)


@pytest.mark.asyncio
async def test_keyboard_only_covers_submit_cancel_and_approval(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer")
        composer.load_text("hello")
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["hello"]
        app.controller.mark_active("run_1")
        captured: list[object] = []
        app.bridge.submit = captured.append  # type: ignore[method-assign]
        await pilot.press("escape")
        await pilot.pause()
        assert captured == [CancelActiveRun(run_id="run_1")]
        captured.clear()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert captured == [CancelActiveRun(run_id="run_1")]
        block = TimelineBlock(
            block_id="approval_1",
            run_id="run_1",
            kind=BlockKind.APPROVAL,
            title="Approval required · changeset · low",
            body="review",
            status=BlockStatus.PENDING,
            expanded=True,
            ref_id="approval_1",
        )
        app.query_one("#timeline").apply((AppendBlock(block=block),))
        await pilot.pause()
        widget = app.block("approval_1")
        assert isinstance(widget, ApprovalBlockWidget)
        assert widget.focused_decision == "cancel"
        await pilot.press("tab")
        await pilot.pause()
