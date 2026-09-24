from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame, StreamFrameType
from vera.models.base import FakeModelAdapter
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.bridge import RuntimeOutputReceived
from vera.terminal.widgets.blocks import TimelineBlockWidget
from vera.terminal.widgets.timeline import ConversationTimeline
from vera.tools.registry import ToolRegistry


def make_app(tmp_path: Path, *, animations: bool) -> VeraTerminalApp:
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
        RuntimeDependencies(runtime=runtime, config=config), workspace, "fake"
    )
    return VeraTerminalApp(controller, workspace, "fake", animations=animations)


def assistant(
    body: str, *, block_id: str = "reply", status: BlockStatus = BlockStatus.RUNNING
) -> TimelineBlock:
    return TimelineBlock(
        block_id=block_id,
        run_id="run_1",
        kind=BlockKind.ASSISTANT,
        title="Vera",
        body=body,
        status=status,
        expanded=True,
    )


def visible_body(widget: TimelineBlockWidget) -> str:
    return widget._body.render().plain


def event(kind: str, sequence: int, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=kind,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_multiline_reply_reveals_rows_while_preserving_full_block(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"line {index}" for index in range(1, 21))
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one(ConversationTimeline)
        timeline.queue_assistant(assistant(body))
        await pilot.pause()
        widget = timeline.block_widget("reply")
        assert widget.block.body == body
        assert "line 1" in visible_body(widget)
        assert "line 20" not in visible_body(widget)
        timeline.finish_reveal()
        assert "line 20" in visible_body(widget)


@pytest.mark.asyncio
async def test_done_waits_for_visible_reply_and_is_retained(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"line {index}" for index in range(1, 21))
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one(ConversationTimeline)
        timeline.queue_assistant(assistant(body))
        timeline.mark_outcome("run_1", "done")
        await pilot.pause()
        assert not list(timeline.query(".run-outcome"))
        timeline.finish_reveal()
        await pilot.pause()
        assert "Done" in str(list(timeline.query(".run-outcome"))[0].render())


@pytest.mark.asyncio
async def test_final_message_replaces_partial_text_without_duplication(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one(ConversationTimeline)
        timeline.queue_assistant(assistant("draft\nline"))
        timeline.queue_assistant(assistant("final\nanswer", status=BlockStatus.SUCCEEDED))
        timeline.finish_reveal()
        await pilot.pause()
        widget = timeline.block_widget("reply")
        assert widget.block.body == "final\nanswer"
        assert "final" in visible_body(widget)
        assert "draft" not in visible_body(widget)
        assert (
            sum(
                item.block.kind is BlockKind.ASSISTANT
                for item in timeline.query(TimelineBlockWidget)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_reduced_motion_shows_full_reply_immediately(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one(ConversationTimeline)
        timeline.queue_assistant(assistant("first\nsecond\nthird"))
        await pilot.pause()
        assert "third" in visible_body(timeline.block_widget("reply"))
        assert timeline.has_pending_reveal is False


@pytest.mark.asyncio
async def test_runtime_events_keep_replying_until_visible_done(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"line {index}" for index in range(1, 21))
    async with app.run_test(size=(80, 24)) as pilot:
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.started", 1)))
        app.on_runtime_output_received(RuntimeOutputReceived(event("model.requested", 2)))
        app.on_runtime_output_received(
            RuntimeOutputReceived(
                StreamFrame(
                    run_id="run_1",
                    stream_id="stream_1",
                    index=0,
                    type=StreamFrameType.ASSISTANT_DELTA,
                    payload={"text": body},
                )
            )
        )
        assert app.activity.current.phase == "replying"
        app.on_runtime_output_received(
            RuntimeOutputReceived(
                event("assistant.message", 3, {"content": body, "stream_id": "stream_1"})
            )
        )
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.completed", 4)))
        await pilot.pause()
        timeline = app.query_one(ConversationTimeline)
        assert timeline.has_pending_reveal is True
        assert not list(timeline.query(".run-outcome"))
        assert not any(
            widget.block.title == "任务完成" for widget in timeline.query(TimelineBlockWidget)
        )
        assert app._last_copyable_text() == body
        assert "正在回复" in str(app.query_one("#work-rail").render())
        app._session_status = app.controller.session_status()
        timeline.finish_reveal()
        app._tick_status()
        await pilot.pause()
        assert "Done" in str(list(timeline.query(".run-outcome"))[0].render())
        assert not any(
            widget.block.title == "任务完成" for widget in timeline.query(TimelineBlockWidget)
        )
        assert app.query_one("#work-rail").display is False


@pytest.mark.asyncio
async def test_approval_flushes_pending_reply_before_prompt(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"line {index}" for index in range(1, 21))
    async with app.run_test(size=(80, 24)):
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.started", 1)))
        app.on_runtime_output_received(RuntimeOutputReceived(event("model.requested", 2)))
        app.on_runtime_output_received(
            RuntimeOutputReceived(
                StreamFrame(
                    run_id="run_1",
                    stream_id="stream_1",
                    index=0,
                    type=StreamFrameType.ASSISTANT_DELTA,
                    payload={"text": body},
                )
            )
        )
        timeline = app.query_one(ConversationTimeline)
        assert timeline.has_pending_reveal is True
        app.on_runtime_output_received(
            RuntimeOutputReceived(event("approval.required", 3, {"approval_id": "a1"}))
        )
        assert timeline.has_pending_reveal is False


@pytest.mark.asyncio
async def test_nonstream_reply_is_paced_and_done_waits(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"section {index}" for index in range(1, 17))
    async with app.run_test(size=(80, 24)) as pilot:
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.started", 1)))
        app.on_runtime_output_received(
            RuntimeOutputReceived(event("assistant.message", 2, {"content": body}))
        )
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.completed", 3)))
        await pilot.pause()
        timeline = app.query_one(ConversationTimeline)
        widget = timeline.block_widget("run_1:2:assistant")
        assert widget.block.body == body
        assert "section 16" not in visible_body(widget)
        assert not list(timeline.query(".run-outcome"))
        timeline.finish_reveal()
        await pilot.pause()
        assert "section 16" in visible_body(widget)
        assert "Done" in str(list(timeline.query(".run-outcome"))[0].render())


@pytest.mark.asyncio
async def test_done_without_reply_is_retained_as_single_timeline_row(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    async with app.run_test(size=(80, 24)) as pilot:
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.started", 1)))
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.completed", 2)))
        await pilot.pause()
        timeline = app.query_one(ConversationTimeline)
        assert len(list(timeline.query(".run-outcome"))) == 1
        assert "Done" in str(list(timeline.query(".run-outcome"))[0].render())


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
async def test_urgent_terminal_event_flushes_reply_and_shows_outcome(
    tmp_path: Path, outcome: str
) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"line {index}" for index in range(1, 21))
    async with app.run_test(size=(80, 24)) as pilot:
        app.on_runtime_output_received(RuntimeOutputReceived(event("run.started", 1)))
        app.on_runtime_output_received(
            RuntimeOutputReceived(event("assistant.message", 2, {"content": body}))
        )
        timeline = app.query_one(ConversationTimeline)
        assert timeline.has_pending_reveal
        app.on_runtime_output_received(RuntimeOutputReceived(event(f"run.{outcome}", 3)))
        await pilot.pause()
        assert not timeline.has_pending_reveal
        assert "line 20" in visible_body(timeline.block_widget("run_1:2:assistant"))
        assert outcome.title() in str(list(timeline.query(".run-outcome"))[0].render())


@pytest.mark.asyncio
async def test_reveal_does_not_pull_reader_back_to_tail(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = "\n\n".join(f"line {index}" for index in range(1, 81))
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one(ConversationTimeline)
        timeline.queue_assistant(assistant(body))
        timeline.finish_reveal()
        await pilot.pause()
        assert timeline.max_scroll_y > 0
        timeline.mark_user_scrolled()
        timeline.scroll_home(animate=False)
        await pilot.pause()
        before = timeline.scroll_y
        timeline.queue_assistant(assistant(body + "\n\nlast line"))
        timeline.advance_reveal()
        await pilot.pause()
        assert timeline.scroll_y == before
        assert timeline.follow_tail is False


@pytest.mark.asyncio
async def test_resize_reflows_paced_markdown_without_losing_content(tmp_path: Path) -> None:
    app = make_app(tmp_path, animations=True)
    body = (
        "A long paragraph that wraps at narrow terminal widths and stays readable.\n\n"
        "```python\nprint('complete')\n```\n\n"
        "| key | value |\n| --- | --- |\n| final | retained |"
    )
    async with app.run_test(size=(120, 40)) as pilot:
        timeline = app.query_one(ConversationTimeline)
        timeline.queue_assistant(assistant(body))
        assert timeline.has_pending_reveal
        await pilot.resize_terminal(60, 16)
        await pilot.pause()
        widget = timeline.block_widget("reply")
        timeline.finish_reveal()
        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        assert widget.block.body == body
        assert "complete" in visible_body(widget)
        assert "retained" in visible_body(widget)
