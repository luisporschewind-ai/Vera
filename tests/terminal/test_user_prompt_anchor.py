from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock, format_block_clock
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.composer import select_composer_prompt
from vera.terminal.widgets.user_prompt_anchor import UserPromptAnchor
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


def user_block(block_id: str, body: str, occurred_at: datetime) -> TimelineBlock:
    return TimelineBlock(
        block_id=block_id,
        run_id="run_1",
        kind=BlockKind.USER,
        title="用户",
        body=body,
        status=BlockStatus.SUCCEEDED,
        expanded=True,
        occurred_at=occurred_at,
    )


def filler(index: int) -> TimelineBlock:
    return TimelineBlock(
        block_id=f"a{index}",
        run_id="run_1",
        kind=BlockKind.ASSISTANT,
        title="助手",
        body="line\n" * 8,
        status=BlockStatus.SUCCEEDED,
        expanded=True,
    )


async def settle_scrolled_off_anchor(pilot, app: VeraTerminalApp) -> UserPromptAnchor:
    timeline = app.query_one("#timeline")
    sticky = app.query_one("#user-sticky", UserPromptAnchor)
    timeline.scroll_end(animate=False)
    for _ in range(8):
        timeline.refresh_user_sticky()
        await pilot.pause()
        if sticky.display is True:
            return sticky
    return sticky


@pytest.mark.asyncio
async def test_anchor_hidden_while_user_still_visible(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    stamp = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one("#timeline").apply((AppendBlock(block=user_block("u1", "可见", stamp)),))
        await pilot.pause()
        sticky = app.query_one("#user-sticky", UserPromptAnchor)
        assert sticky.display is False


@pytest.mark.asyncio
async def test_anchor_appears_after_user_scrolls_off_and_keeps_original_time(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    first_at = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    second_at = datetime(2026, 9, 15, 2, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=user_block("u1", "第一问", first_at)),
                *(AppendBlock(block=filler(index)) for index in range(20)),
                AppendBlock(block=user_block("u2", "第二问", second_at)),
                *(AppendBlock(block=filler(index + 20)) for index in range(20)),
            )
        )
        sticky = await settle_scrolled_off_anchor(pilot, app)
        assert sticky.display is True
        assert sticky.body_text == "第二问"
        assert sticky.clock_text == format_block_clock(second_at)
        assert sticky.clock_text != ""
        assert "AM" not in sticky.clock_text
        assert sticky.query_one("#user-sticky-prompt").region.x >= 0


@pytest.mark.asyncio
async def test_anchor_hides_when_scrolled_back_to_original(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    stamp = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=user_block("u1", "锚点", stamp)),
                *(AppendBlock(block=filler(index)) for index in range(40)),
            )
        )
        sticky = await settle_scrolled_off_anchor(pilot, app)
        assert sticky.display is True
        timeline.scroll_home(animate=False)
        timeline.refresh_user_sticky()
        await pilot.pause()
        assert sticky.display is False or sticky.body_text in {"", "锚点"}


@pytest.mark.asyncio
async def test_clear_hides_anchor(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    stamp = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply((AppendBlock(block=user_block("u1", "旧", stamp)),))
        await pilot.pause()
        timeline.clear_blocks()
        await pilot.pause()
        sticky = app.query_one("#user-sticky", UserPromptAnchor)
        assert sticky.display is False
        assert sticky.body_text == ""


@pytest.mark.asyncio
async def test_narrow_terminal_compacts_then_hides_anchor(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    stamp = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=user_block("u1", "窄屏", stamp)),
                *(AppendBlock(block=filler(index)) for index in range(40)),
            )
        )
        sticky = await settle_scrolled_off_anchor(pilot, app)
        assert sticky.display is True
        await pilot.resize_terminal(60, 16)
        await pilot.pause()
        assert sticky.display is True
        assert sticky.styles.height.value == 1 or str(sticky.styles.height) in {"1", "1h"}
        await pilot.resize_terminal(50, 12)
        await pilot.pause()
        assert sticky.display is False
        assert str(app.query_one("#composer-prompt").render()) == select_composer_prompt(
            unicode=True
        )
