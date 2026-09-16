from pathlib import Path

import pytest
from textual.events import Paste

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.actions import SubmitPrompt
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.completions import CompletionList
from vera.terminal.widgets.composer import (
    COMPOSER_PROMPT,
    PromptComposer,
    sanitize_composer_text,
    select_composer_prompt,
)
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
async def test_alt_enter_inserts_newline_and_enter_submits_multiline(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.restore_draft("第一行")
        await pilot.press("alt+enter")
        await pilot.pause()
        assert app.submitted == []
        assert composer.text.startswith("第一行")
        assert "\n" in composer.text
        assert composer.styles.height.value >= 2
        assert app.query_one("#composer-bar").styles.height.value >= 4
        composer.restore_draft("第一行\n第二行")
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["第一行\n第二行"]
        assert composer.text == ""


@pytest.mark.asyncio
async def test_soft_wrapped_text_grows_composer_height(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(40, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        bar = app.query_one("#composer-bar")
        composer.load_text("汉" * 40)
        await pilot.pause()
        composer.sync_multiline_layout()
        await pilot.pause()
        assert "\n" not in composer.text
        assert composer.size.height >= 2
        assert getattr(bar.styles.height, "value", 0) >= 4
        assert bar.outer_size.height >= 4


@pytest.mark.asyncio
async def test_shift_and_cmd_enter_submit_not_newline(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.restore_draft("hello")
        await pilot.press("shift+enter")
        await pilot.pause()
        assert app.submitted == ["hello"]
        composer.restore_draft("again")
        await pilot.press("cmd+enter")
        await pilot.pause()
        assert app.submitted == ["hello", "again"]


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


@pytest.mark.asyncio
async def test_enter_executes_highlighted_slash_match(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.load_text("/th")
        app._refresh_completions(composer.text)
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == []
        assert composer.text == "/theme "
        app._refresh_completions(composer.text)
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["/theme default"]
        assert composer.text == ""
        assert app.query_one("#completions", CompletionList).display is False


@pytest.mark.asyncio
async def test_slash_popup_stays_visible_while_typing(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        completions = app.query_one("#completions", CompletionList)
        await pilot.press("/")
        await pilot.pause()
        assert completions.display is True
        names = [item.name for item in completions._slash_items]
        assert "/doctor" in names
        assert "/theme" in names
        assert completions.size.height >= 3
        assert "斜杠命令" in completions.visible_text()
        await pilot.press("d")
        await pilot.pause()
        assert completions.display is True
        assert "/doctor" in completions.visible_text()
        await pilot.press("o")
        await pilot.pause()
        assert completions.display is True
        assert completions.size.height >= 2
        assert "斜杠命令 · 1" in completions.visible_text()
        assert "检查本地环境与配置" in completions.visible_text()
        assert completions.has_selection_style is True
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["/doctor"]
        assert completions.display is False


@pytest.mark.asyncio
async def test_enter_inserts_path_mention_without_submitting(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    (app.workspace / "ViewController.swift").write_text("x", encoding="utf-8")
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        completions = app.query_one("#completions", CompletionList)
        composer.load_text("@")
        app._refresh_completions(composer.text)
        await pilot.pause()
        assert completions.display is True
        assert completions._mode == "path"
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == []
        assert composer.text == "@ViewController.swift "
        assert completions.display is False
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["@ViewController.swift"]
        assert composer.text == ""


@pytest.mark.asyncio
async def test_nested_path_mention_submits_prompt_not_slash_command(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    nested = app.workspace / "App"
    nested.mkdir()
    (nested / "ViewController.swift").write_text("x", encoding="utf-8")
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        captured: list[object] = []
        app.bridge.submit = captured.append  # type: ignore[method-assign]
        composer.load_text("@App/ViewController.swift 分析此文件")
        app._refresh_completions(composer.text)
        await pilot.pause()
        assert composer.text == "@App/ViewController.swift 分析此文件"
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["@App/ViewController.swift 分析此文件"]
        assert captured == [SubmitPrompt(text="@App/ViewController.swift 分析此文件")]
        assert composer.text == ""


@pytest.mark.asyncio
async def test_slash_popup_survives_when_input_loses_slash(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        completions = app.query_one("#completions", CompletionList)
        await pilot.press("/")
        await pilot.pause()
        while completions._slash_items[completions._selected].name != "/doctor":
            await pilot.press("down")
        composer.load_text("do")
        await pilot.pause()
        assert composer.text == "/do"
        assert completions.display is True
        assert "/doctor" in completions.visible_text()


@pytest.mark.asyncio
async def test_composer_shows_prompt_glyph_left_of_input(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        prompt = app.query_one("#composer-prompt")
        bar = app.query_one("#composer-bar")
        composer.restore_draft("hello")
        await pilot.pause()
        glyph = select_composer_prompt(unicode=True)
        assert str(prompt.render()) == glyph
        assert composer.text == "hello"
        assert glyph not in composer.text
        assert COMPOSER_PROMPT not in composer.text or glyph == COMPOSER_PROMPT
        assert prompt.region.x < composer.region.x
        assert prompt.region.y == composer.region.y
        assert bar.region.x >= 2
        assert bar.styles.margin.left == 2
        assert bar.styles.margin.right == 2
        assert "round" in str(bar.styles.border).lower()
        assert composer.highlight_cursor_line is False
        composer_bg = composer.styles.background
        assert composer_bg.a == 0 or str(composer_bg).lower() == "transparent"
        prompt_bg = prompt.styles.background
        assert prompt_bg.a == 0 or str(prompt_bg).lower() == "transparent"
        composer.submit()
        await pilot.pause()
        assert app.submitted == ["hello"]
        assert str(prompt.render()) == glyph


@pytest.mark.asyncio
async def test_ascii_prompt_glyph_when_unicode_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vera.terminal.capabilities import detect_display_capabilities

    monkeypatch.setattr(
        "vera.terminal.app.detect_display_capabilities",
        lambda **kwargs: detect_display_capabilities(
            environ={"TERM": "dumb"},
            stdout_tty=True,
            animations_config=kwargs.get("animations_config", True),
        ),
    )
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert str(app.query_one("#composer-prompt").render()) == COMPOSER_PROMPT
        assert COMPOSER_PROMPT not in app.query_one("#composer", PromptComposer).text
