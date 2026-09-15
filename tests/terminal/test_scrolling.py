from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock, format_block_clock
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.blocks import UserBlockWidget
from vera.terminal.widgets.composer import COMPOSER_PROMPT
from vera.terminal.widgets.user_sticky import UserStickyBar
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
        kind=BlockKind.ASSISTANT,
        title=f"助手-{index}",
        body="\n".join(f"line-{index}-{row}" for row in range(4)),
        status=BlockStatus.SUCCEEDED,
        expanded=True,
    )


@pytest.mark.asyncio
async def test_follow_tail_reaches_real_bottom_without_manual_scroll(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(tuple(AppendBlock(block=make_block(i)) for i in range(40)))
        await pilot.pause()
        assert timeline.max_scroll_y > 0
        assert timeline.scroll_y == timeline.max_scroll_y

        timeline.apply((AppendBlock(block=make_block(40)),))
        await pilot.pause()
        assert timeline.scroll_y == timeline.max_scroll_y


@pytest.mark.asyncio
async def test_follow_tail_survives_event_by_event_arrival(tmp_path: Path) -> None:
    """Real runs deliver one RuntimeOutput per message, not a batch."""

    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        for index in range(1, 31):
            app.append_output(
                EventEnvelope(
                    event_id=f"e{index}",
                    run_id="run_1",
                    sequence=index,
                    timestamp=datetime.now(UTC),
                    type="assistant.message",
                    payload={"text": "\n".join(f"done-{index}-{row}" for row in range(4))},
                )
            )
            await pilot.pause()
        assert timeline.max_scroll_y > 0
        assert timeline.scroll_y == timeline.max_scroll_y


@pytest.mark.asyncio
async def test_streaming_updates_follow_tail_to_real_bottom(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(tuple(AppendBlock(block=make_block(i)) for i in range(30)))
        await pilot.pause()
        growing = TimelineBlock(
            block_id="assistant_stream",
            run_id="run_1",
            kind=BlockKind.ASSISTANT,
            title="助手",
            body="\n".join(f"streamed-{i}" for i in range(40)),
            status=BlockStatus.RUNNING,
            expanded=True,
        )
        timeline.apply_streaming_update(growing)
        timeline.flush_scheduled()
        await pilot.pause()
        assert timeline.scroll_y == timeline.max_scroll_y


@pytest.mark.asyncio
async def test_return_to_tail_reaches_real_bottom(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(tuple(AppendBlock(block=make_block(i)) for i in range(40)))
        await pilot.pause()
        timeline.scroll_to(y=0, animate=False)
        timeline.mark_user_scrolled()
        await pilot.pause()
        timeline.apply((AppendBlock(block=make_block(99)),))
        await pilot.pause()
        timeline.return_to_tail()
        await pilot.pause()
        assert timeline.scroll_y == timeline.max_scroll_y
        assert timeline.follow_tail is True


@pytest.mark.asyncio
async def test_scroll_up_at_tail_does_not_unpin_follow(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(tuple(AppendBlock(block=make_block(i)) for i in range(40)))
        await pilot.pause()
        assert timeline.scroll_y == timeline.max_scroll_y

        class _Event:
            def __init__(self) -> None:
                self.stopped = False

            def stop(self) -> None:
                self.stopped = True

        up = _Event()
        down = _Event()
        timeline.on_mouse_scroll_up(up)
        timeline.on_mouse_scroll_down(down)
        await pilot.pause()
        assert up.stopped is True
        assert down.stopped is True
        assert timeline.follow_tail is True
        timeline.apply((AppendBlock(block=make_block(40)),))
        await pilot.pause()
        assert timeline.scroll_y == timeline.max_scroll_y
        assert timeline.pending_update_count == 0


@pytest.mark.asyncio
async def test_new_output_does_not_steal_scroll_position(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(tuple(AppendBlock(block=make_block(i)) for i in range(40)))
        await pilot.pause()
        timeline.scroll_end(animate=False)
        await pilot.pause()
        timeline.scroll_to(y=0, animate=False)
        timeline.mark_user_scrolled()
        await pilot.pause()
        before = timeline.scroll_y
        app.append_output(
            EventEnvelope(
                event_id="e1",
                run_id="run_1",
                sequence=1,
                timestamp=datetime.now(UTC),
                type="assistant.message",
                payload={"text": "\n".join(f"queued-{row}" for row in range(4))},
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
        app._clear_timeline_display()
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
        assert timeline.styles.scrollbar_size_vertical == 0
        assert timeline.scrollbar_size_vertical == 0


def _luma(color: object) -> int:
    rgb = getattr(color, "rgb", None)
    if rgb is None:
        return 0
    return int(rgb[0]) + int(rgb[1]) + int(rgb[2])


def user_block(block_id: str, body: str, created_at: datetime) -> TimelineBlock:
    return TimelineBlock(
        block_id=block_id,
        run_id="run_1",
        kind=BlockKind.USER,
        title="用户",
        body=body,
        status=BlockStatus.SUCCEEDED,
        expanded=True,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_user_message_shows_clock_on_the_right(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    created = datetime(2026, 9, 15, 8, 4, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply((AppendBlock(block=user_block("u1", "你好vera", created)),))
        await pilot.pause()
        widget = app.block("u1")
        clock = format_block_clock(created)
        assert isinstance(widget, UserBlockWidget)
        assert clock in str(widget._time.render())
        assert clock.endswith(" AM") or clock.endswith(" PM")
        assert _luma(widget._time.styles.color) < _luma(widget.styles.color)
        assert "你好vera" in str(widget._body.render())
        assert str(widget._title.render()) == COMPOSER_PROMPT
        assert widget._time.region.x > widget._body.region.x
        assert widget.region.x >= 2
        composer = app.query_one("#composer-bar")
        assert widget.region.x == composer.region.x
        assert widget.styles.margin.left == composer.styles.margin.left
        assert widget.styles.margin.right == composer.styles.margin.right
        assert _luma(widget.styles.color) >= 720
        border = str(widget.styles.border).lower()
        assert "round" not in border
        assert "inner" not in border
        assert "tall" not in border
        assert widget.styles.padding.top == 1
        assert widget.styles.padding.bottom == 1
        assert widget.outer_size.height >= 3
        assert widget.styles.margin.top == 1
        assert widget.styles.margin.bottom == 1
        assert widget.styles.margin.left == 2
        assert widget.styles.margin.right == 2
        sticky = app.query_one("#user-sticky", UserStickyBar)
        assert sticky.display is False


@pytest.mark.asyncio
async def test_timeline_and_composer_share_horizontal_inset(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    created = datetime(2026, 9, 15, 8, 4, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=user_block("u1", "你好", created)),
                AppendBlock(block=make_block(0)),
            )
        )
        await pilot.pause()
        user = app.block("u1")
        assistant = app.block("b0")
        composer = app.query_one("#composer-bar")
        assert user.region.x == composer.region.x
        assert user.region.right == composer.region.right
        assert assistant.region.x == composer.region.x
        assert user.region.x == timeline.region.x + 2
        assert timeline.region.width - user.region.right == 2
        assert user.region.x == app.screen.size.width - user.region.right
        title = assistant.query_one(".block-title")
        body = assistant.query_one(".block-body")
        assert title.region.x == body.region.x
        assert _luma(user.styles.color) > _luma(body.styles.color)


@pytest.mark.asyncio
async def test_user_cards_keep_fixed_vertical_gap(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    created = datetime(2026, 9, 15, 8, 4, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=user_block("u1", "短", created)),
                AppendBlock(
                    block=user_block(
                        "u2",
                        "这是一条明显更长的用户消息，用来确认卡片仍同宽",
                        created,
                    )
                ),
            )
        )
        await pilot.pause()
        first = app.block("u1")
        second = app.block("u2")
        for widget in (first, second):
            assert widget.styles.margin.top == 1
            assert widget.styles.margin.bottom == 1
            assert widget.styles.margin.left == 2
            assert widget.styles.margin.right == 2
            assert "round" not in str(widget.styles.border).lower()
            assert widget.styles.padding.top == 1
            assert widget.styles.padding.bottom == 1
            assert widget.outer_size.height >= 3
            assert "1fr" in str(widget.styles.width).lower()
        assert second.region.y - first.region.bottom == 1
        assert first.region.y >= timeline.region.y + 1
        assert first.region.x == second.region.x
        assert first.region.width == second.region.width
        assert first._time.region.right == second._time.region.right


@pytest.mark.asyncio
async def test_scrolled_off_user_sticks_until_replaced(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    first_at = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    second_at = datetime(2026, 9, 15, 2, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        mutations = [
            AppendBlock(block=user_block("u1", "第一问", first_at)),
            *(AppendBlock(block=make_block(index)) for index in range(20)),
            AppendBlock(block=user_block("u2", "第二问", second_at)),
            *(AppendBlock(block=make_block(index + 20)) for index in range(20)),
        ]
        timeline.apply(tuple(mutations))
        await pilot.pause()
        sticky = app.query_one("#user-sticky", UserStickyBar)
        assert sticky.display is True
        assert sticky.body_text == "第二问"
        assert sticky.clock_text == format_block_clock(second_at)
        header = app.query_one("#header")
        composer = app.query_one("#composer-bar")
        assert header.region.y == 0
        assert sticky.region.y >= header.region.bottom
        assert sticky.outer_size.height == 3
        assert sticky.region.x == composer.region.x
        assert sticky.styles.margin.left == composer.styles.margin.left
        assert sticky.styles.margin.right == composer.styles.margin.right
        border = str(sticky.styles.border).lower()
        assert "round" not in border
        assert "inner" not in border
        assert sticky.styles.padding.top == 1
        assert sticky.styles.padding.bottom == 1
        assert str(sticky.query_one("#user-sticky-prompt").render()) == COMPOSER_PROMPT

        app.block("u2").scroll_visible(top=True, animate=False)
        await pilot.pause()
        timeline.refresh_user_sticky()
        assert sticky.body_text == "第一问"
        assert sticky.clock_text == format_block_clock(first_at)

        timeline.scroll_home(animate=False)
        await pilot.pause()
        timeline.refresh_user_sticky()
        assert sticky.display is False
