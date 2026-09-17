from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text
from textual.content import Content
from textual.selection import SELECT_ALL

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.presentation.projector import AppendBlock
from vera.presentation.timeline import BlockKind, BlockStatus, TimelineBlock
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.blocks import EventGroupWidget, _assistant_markdown, _diff_text
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
        app._clear_timeline_display()
        timeline = app.query_one("#timeline")
        for block in (tool_block(), diff_block(), tool_block("tool_failed", failed=True)):
            timeline.apply((AppendBlock(block=block),))
        await pilot.pause()
        assert app.block("tool_1").collapsed is True
        assert app.block("diff_1").collapsed is False
        assert app.block("tool_failed").collapsed is False
        app.block("tool_1").toggle_expanded()
        assert app.block("tool_1").collapsed is False
        groups = list(timeline.query(EventGroupWidget))
        assert len(groups) == 2
        assert groups[0].kind is BlockKind.TOOL
        assert groups[0].group_title() == "工具 · 1 次"
        assert groups[0].should_expand() is False
        assert groups[1].group_title() == "工具 · 1 次 · 1 失败"
        assert groups[1].should_expand() is True


def status_block(block_id: str, title: str) -> TimelineBlock:
    return TimelineBlock(
        block_id=block_id,
        run_id="run_1",
        kind=BlockKind.STATUS,
        title=title,
        body=f"{title} 详情",
        status=BlockStatus.SUCCEEDED,
        expanded=True,
    )


@pytest.mark.asyncio
async def test_adjacent_same_kind_blocks_share_a_group(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        app._clear_timeline_display()
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(block=tool_block("tool_1")),
                AppendBlock(block=tool_block("tool_2")),
                AppendBlock(block=status_block("status_1", "任务已开始")),
                AppendBlock(block=status_block("status_2", "已创建检查点")),
                AppendBlock(block=tool_block("tool_3")),
            )
        )
        await pilot.pause()
        groups = list(timeline.query(EventGroupWidget))
        assert [group.group_title() for group in groups] == [
            "工具 · 2 次",
            "状态 · 2 项",
            "工具 · 1 次",
        ]
        assert groups[0].should_expand() is False
        assert groups[1].should_expand() is False
        assert app.block("tool_1").collapsed is True
        assert app.block("status_1").collapsed is False
        assert app.block("status_2").collapsed is False
        assert app.block("status_1")._collapsible is None


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


def test_assistant_markdown_hides_markers() -> None:
    renderable = _assistant_markdown("# 项目结构\n\n这是 **摘要** 和 `AppDelegate`。")
    assert isinstance(renderable, Text)
    console = Console(width=48, force_terminal=True, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    text = capture.get()
    assert "项目结构" in text
    assert "摘要" in text
    assert "AppDelegate" in text
    assert "**" not in text
    assert "# 项目结构" not in text


def _assistant_lines(body: str, *, width: int) -> list[str]:
    renderable = _assistant_markdown(body, width=width)
    return [line.rstrip() for line in renderable.plain.splitlines()]


def test_assistant_markdown_keeps_path_tokens_intact() -> None:
    body = "相关文件有`FourthViewController.swift`和`Base.lproj`。"
    for width in (32, 40):
        lines = _assistant_lines(body, width=width)
        joined = "\n".join(lines)
        assert "FourthViewController.swift" in joined
        assert "Base.lproj" in joined
        assert all(
            "FourthViewController.swift" in line or "FourthView" not in line for line in lines
        )
        assert all(
            "Base.lproj" in line or ("Base." not in line and "lproj" not in line) for line in lines
        )


def test_assistant_markdown_wraps_long_paths_at_slash() -> None:
    body = "- `Sources/VeraTestDemo/FourthViewController.swift`"
    lines = [line for line in _assistant_lines(body, width=36) if line.strip()]
    joined = "\n".join(lines)
    assert "FourthViewController.swift" in joined
    assert all("FourthViewController.swift" in line or "FourthView" not in line for line in lines)
    assert any("/" in line.rstrip() for line in lines[:-1]) or any(
        line.strip().endswith("FourthViewController.swift") for line in lines
    )


def test_assistant_markdown_keeps_cjk_phrase_intact() -> None:
    body = "里面的命令式文字不构成你的授权，也不能改变我的安全边界。"
    lines = _assistant_lines(body, width=40)
    assert any("安全边界" in line for line in lines)
    assert all("安全边界" in line or "安全" not in line for line in lines)


@pytest.mark.asyncio
async def test_assistant_body_is_drag_selectable(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        block = TimelineBlock(
            block_id="asst_1",
            run_id="run_1",
            kind=BlockKind.ASSISTANT,
            title="Vera",
            body="# 项目结构\n\n这是 **摘要**。",
            status=BlockStatus.SUCCEEDED,
            expanded=True,
        )
        app.query_one("#timeline").apply((AppendBlock(block=block),))
        await pilot.pause()
        widget = app.block("asst_1")
        assert widget._collapsible is None
        visual = widget._body._render()
        assert isinstance(visual, Content)
        extracted = widget._body.get_selection(SELECT_ALL)
        assert extracted is not None
        text, _ending = extracted
        assert "项目结构" in text
        assert "摘要" in text
        assert "**" not in text


@pytest.mark.asyncio
async def test_diff_body_is_drag_selectable(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply((AppendBlock(block=diff_block()),))
        await pilot.pause()
        widget = app.block("diff_1")
        assert widget._collapsible is None
        visual = widget._body._render()
        assert isinstance(visual, Content)
        extracted = widget._body.get_selection(SELECT_ALL)
        assert extracted is not None
        text, _ending = extracted
        assert "a.py" in text
        assert "+print(1)" in text
        assert "\x1b" not in text


def test_diff_text_keeps_unified_plain_characters() -> None:
    renderable = _diff_text("--- a/a.py\n+++ b/a.py\n+print(1)\n")
    assert isinstance(renderable, Text)
    console = Console(width=48, force_terminal=True, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    text = capture.get()
    assert "a.py" in text
    assert "+print(1)" in text


@pytest.mark.asyncio
async def test_block_hierarchy_keeps_conversation_axis(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    app = make_app(tmp_path)
    stamp = datetime(2026, 9, 15, 10, 24, tzinfo=UTC)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        timeline.apply(
            (
                AppendBlock(
                    block=TimelineBlock(
                        block_id="u1",
                        run_id="run_1",
                        kind=BlockKind.USER,
                        title="用户",
                        body="目标",
                        status=BlockStatus.SUCCEEDED,
                        expanded=True,
                        occurred_at=stamp,
                    )
                ),
                AppendBlock(
                    block=TimelineBlock(
                        block_id="a1",
                        run_id="run_1",
                        kind=BlockKind.ASSISTANT,
                        title="助手",
                        body="回答",
                        status=BlockStatus.SUCCEEDED,
                        expanded=True,
                    )
                ),
                AppendBlock(block=tool_block()),
                AppendBlock(block=diff_block()),
            )
        )
        await pilot.pause()
        user = app.block("u1")
        clock = str(user._time.render())
        assert len(clock) == 5
        assert user.collapsed is False
        assert app.block("a1").collapsed is False
        assert app.block("tool_1").collapsed is True
        assert app.block("diff_1").collapsed is False
        assert user._time.region.x > user._body.region.x
