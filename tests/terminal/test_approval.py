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
        widget.mark_expired()
        assert widget._locked is True
        assert "过期" in widget.block.title


def _pending_approval() -> EventEnvelope:
    return EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="approval.required",
        payload={"approval_id": "approval_1"},
    )


def _approval_block() -> TimelineBlock:
    return TimelineBlock(
        block_id="approval_1",
        run_id="run_1",
        kind=BlockKind.APPROVAL,
        title="Approval required · changeset · low",
        body="review",
        status=BlockStatus.PENDING,
        expanded=True,
        ref_id="approval_1",
    )


@pytest.mark.asyncio
async def test_approval_tab_cycles_only_decision_buttons(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    controller._pending_approval = _pending_approval()
    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one("#timeline").apply((AppendBlock(block=_approval_block()),))
        await pilot.pause()
        widget = app.block("approval_1")
        assert isinstance(widget, ApprovalBlockWidget)
        widget.focus_default_action()
        await pilot.pause()
        assert app.focused is widget._cancel
        assert widget.focused_decision == "cancel"
        assert widget._cancel.variant == "primary"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is widget._reject
        assert widget.focused_decision == "reject"
        assert widget._reject.variant == "primary"
        assert widget._cancel.variant == "default"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is widget._approve
        assert widget.focused_decision == "approve"
        assert widget._approve.variant == "primary"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is widget._cancel
        assert widget.focused_decision == "cancel"
        await pilot.press("shift+tab")
        await pilot.pause()
        assert app.focused is widget._approve
        assert widget.focused_decision == "approve"


@pytest.mark.asyncio
async def test_approval_does_not_leave_interrupting_gap(tmp_path: Path) -> None:
    app, _controller = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        status = TimelineBlock(
            block_id="status_1",
            run_id="run_1",
            kind=BlockKind.STATUS,
            title="状态",
            body="running",
            status=BlockStatus.RUNNING,
            expanded=True,
        )
        assistant = TimelineBlock(
            block_id="assistant_1",
            run_id="run_1",
            kind=BlockKind.ASSISTANT,
            title="助手",
            body="done",
            status=BlockStatus.SUCCEEDED,
            expanded=True,
        )
        timeline.apply(
            (
                AppendBlock(block=status),
                AppendBlock(block=_approval_block()),
                AppendBlock(block=assistant),
            )
        )
        await pilot.pause()
        previous = app.block("status_1")
        widget = app.block("approval_1")
        following = app.block("assistant_1")
        assert isinstance(widget, ApprovalBlockWidget)
        assert widget.styles.margin.bottom == 0
        assert widget.styles.margin.top == 0
        assert widget._cancel.size.height <= 1
        assert widget.region.y - previous.region.bottom <= 1
        assert following.region.y - widget.region.bottom <= 1


@pytest.mark.asyncio
async def test_approval_card_shows_full_body_and_actions(tmp_path: Path) -> None:
    app, _controller = make_app(tmp_path)
    body = "动作 changeset\n目标 notes.md\n风险 low\n工作区 /tmp/workspace\n效果 写入文件"
    block = TimelineBlock(
        block_id="approval_1",
        run_id="run_1",
        kind=BlockKind.APPROVAL,
        title="Approval required · changeset · low",
        body=body,
        status=BlockStatus.PENDING,
        expanded=True,
        ref_id="approval_1",
    )
    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one("#timeline").apply((AppendBlock(block=block),))
        await pilot.pause()
        widget = app.block("approval_1")
        assert isinstance(widget, ApprovalBlockWidget)
        rendered = str(widget._body.render())
        for line in body.split("\n"):
            assert line in rendered
        assert widget.size.height >= 6
        for button, label in (
            (widget._cancel, "Cancel"),
            (widget._reject, "Reject"),
            (widget._approve, "Approve"),
        ):
            assert label in str(button.label)
            assert button.size.height >= 1
            assert button.region.y >= widget.region.y
            assert button.region.bottom <= widget.region.bottom + 1
            assert button.region.x >= widget.region.x
            assert button.region.right <= widget.region.right + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 16), (80, 24), (120, 40)])
async def test_approval_stays_continuous_across_sizes(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    app, _controller = make_app(tmp_path)
    body = "动作 changeset\n目标 notes.md\n风险 low\n效果 写入文件"
    async with app.run_test(size=size) as pilot:
        app.query_one("#timeline").apply(
            (AppendBlock(block=_approval_block().model_copy(update={"body": body})),)
        )
        await pilot.pause()
        widget = app.block("approval_1")
        assert isinstance(widget, ApprovalBlockWidget)
        rendered = str(widget._body.render())
        assert "风险 low" in rendered
        assert widget.styles.margin.top == 0
        assert widget.styles.margin.bottom == 0
        assert widget._cancel.size.height <= 1
        for button in (widget._cancel, widget._reject, widget._approve):
            assert button.display is True
            assert button.region.y >= widget.region.y
