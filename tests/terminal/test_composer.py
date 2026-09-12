from pathlib import Path

import pytest
from textual.events import Paste

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.composer import PromptComposer, sanitize_composer_text
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
async def test_enter_submits_and_ctrl_j_inserts_newline(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.load_text("hi\nx")
        assert "\n" in composer.text
        composer.submit()
        await pilot.pause()
        assert app.submitted == ["hi\nx"]
        assert composer.text == ""


@pytest.mark.asyncio
async def test_ctrl_j_inserts_newline_action(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.load_text("ab")
        composer.action_insert_newline()
        assert "\n" in composer.text
        await pilot.pause()


@pytest.mark.asyncio
async def test_blank_does_not_submit(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.submit()
        await pilot.pause()
        assert app.submitted == []


def test_sanitize_strips_control_and_keeps_multiline() -> None:
    assert sanitize_composer_text("hello\r\nworld") == "hello\nworld"
    assert "\x1b" not in sanitize_composer_text("\x1b[31mred\x1b[0m")
    assert "secret" in sanitize_composer_text("\x1b]8;;https://evil\x07secret")
    assert sanitize_composer_text("左\u202e右") == "左右"


@pytest.mark.asyncio
async def test_paste_is_one_edit_and_does_not_submit(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.post_message(Paste("第一行\n第二行\n"))
        await pilot.pause()
        assert "第一行" in composer.text
        assert "\n" in composer.text
        assert app.submitted == []


@pytest.mark.asyncio
async def test_history_and_cjk_round_trip(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.load_text("你好世界")
        composer.submit()
        await pilot.pause()
        assert app.submitted == ["你好世界"]
        composer.load_text("")
        composer.load_text(composer.prompt_history.up(""))
        assert composer.text == "你好世界"
        composer.action_cursor_line_start()
        composer.action_cursor_line_end()
        composer.action_search_history()
        assert "你好" in composer.text
