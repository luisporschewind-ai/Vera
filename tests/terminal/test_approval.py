from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ResolveSessionApproval
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.approval import ApprovalBlockWidget
from vera.tools.registry import ToolRegistry


class RecordingController(SessionController):
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.actions: list[object] = []

    def dispatch(self, action):  # type: ignore[no-untyped-def, override]
        self.actions.append(action)
        if False:  # pragma: no cover
            yield


def make_app(tmp_path: Path) -> tuple[VeraTerminalApp, RecordingController]:
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
    controller = RecordingController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake", animations=False), controller


@pytest.mark.asyncio
async def test_approval_focus_defaults_to_cancel(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
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
        widget._cancel.press()
        await pilot.pause()
        assert controller.actions[-1] == ResolveSessionApproval(
            approval_id="approval_1", decision="cancel"
        )
        assert widget._locked is True
