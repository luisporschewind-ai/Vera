from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ExecuteSlashCommand
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.bridge import RuntimeOutputReceived
from vera.terminal.theme import VERA_THEMES, format_theme_status, normalize_theme, theme_class
from vera.tools.registry import ToolRegistry


def test_theme_is_session_only_and_named() -> None:
    assert normalize_theme(None) == "default"
    assert normalize_theme("high-contrast") == "high-contrast"
    assert normalize_theme("no-color") == "no-color"
    assert normalize_theme("executable.py") is None
    assert theme_class("default") == "theme-default"


def test_default_theme_uses_deep_sea_tokens() -> None:
    from vera.terminal.theme import SEMANTIC_TOKENS, TOKEN_NAMES

    for name in ("default", "high-contrast", "no-color"):
        tokens = SEMANTIC_TOKENS[name]
        assert tuple(tokens) == TOKEN_NAMES
    default = next(theme for theme in VERA_THEMES if theme.name == "default")
    assert default.background == "#0B1C28"
    assert default.surface == "#122433"
    assert default.accent == "#3D7A8C"
    assert default.warning == "#B08A4A"
    assert default.error == "#A85A5A"
    assert default.success == "#4A8B6F"
    assert default.foreground == "#D7E4EE"
    assert default.variables["logo"] == "#548EA0"
    high_contrast = next(theme for theme in VERA_THEMES if theme.name == "high-contrast")
    assert high_contrast.accent == "#FFFF00"
    no_color = next(theme for theme in VERA_THEMES if theme.name == "no-color")
    assert no_color.accent == "#B0B0B0"


@pytest.mark.asyncio
async def test_v4_logo_uses_theme_color_and_never_extra_bold(tmp_path: Path) -> None:
    from vera.terminal.widgets.header import VeraHeader

    app = _make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        for name, expected_color in (
            ("default", "#548EA0"),
            ("high-contrast", "#FFFF00"),
            ("no-color", "#B0B0B0"),
        ):
            app._apply_theme(name)
            await pilot.pause()
            header = app.query_one(VeraHeader)
            wordmark = app.query_one("#header-wordmark")
            assert wordmark.styles.color.hex == expected_color
            assert not wordmark.styles.text_style.bold
            header.set_wave_phase(0.5)
            visual = header._logo_visual(header.current_mark().lines)
            if name != "default":
                assert not visual.spans


def test_unknown_theme_is_rejected() -> None:
    assert normalize_theme("neon") is None
    assert normalize_theme("default.sh") is None


def _make_app(tmp_path: Path) -> VeraTerminalApp:
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
async def test_default_theme_is_applied_so_composer_uses_deep_blue(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        app._apply_theme("default")
        await pilot.pause()
        assert app.theme == "default"
        accent = app.get_css_variables().get("accent", "").lower()
        assert accent == "#3d7a8c"
        border = str(app.query_one("#composer-bar").styles.border)
        assert "round" in border.lower()
        assert "61, 122, 140" in border


def test_theme_status_text_is_human_readable() -> None:
    text = format_theme_status("high-contrast")
    assert "当前主题：high-contrast" in text
    assert "高对比" in text
    assert "no-color" in text


@pytest.mark.asyncio
async def test_theme_command_switches_app_theme_and_chrome(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        app._apply_theme("default")
        await pilot.pause()
        for item in app.controller.dispatch(ExecuteSlashCommand(raw="/theme high-contrast")):
            app.on_runtime_output_received(RuntimeOutputReceived(item))
        await pilot.pause()
        assert app.theme == "high-contrast"
        assert "theme-high-contrast" in app.classes
        assert "theme-high-contrast" in app.screen.classes
        accent = app.get_css_variables().get("accent", "").lower()
        assert accent in {"#ffff00", "#feff00"}
        border = str(app.query_one("#composer-bar").styles.border)
        assert "255, 255, 0" in border
        header = str(app.query_one("#header").styles.background)
        assert "0, 0, 0" in header
        welcome = str(app.query_one("#welcome").styles.background)
        assert "0, 0, 0" in welcome
        timeline_border = str(app.query_one("#timeline").styles.border).lower()
        assert "solid" not in timeline_border
        assert "round" not in timeline_border
        for item in app.controller.dispatch(ExecuteSlashCommand(raw="/theme no-color")):
            app.on_runtime_output_received(RuntimeOutputReceived(item))
        await pilot.pause()
        assert app.theme == "no-color"
        border = str(app.query_one("#composer-bar").styles.border)
        assert "176, 176, 176" in border
        assert "theme-no-color" in app.classes
        assert "theme-high-contrast" not in app.classes


@pytest.mark.asyncio
async def test_no_color_env_selects_no_color_theme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vera.terminal.capabilities import detect_display_capabilities

    monkeypatch.setattr(
        "vera.terminal.app.detect_display_capabilities",
        lambda **kwargs: detect_display_capabilities(
            environ={"NO_COLOR": "1", "TERM": "xterm-256color"},
            stdout_tty=True,
            animations_config=kwargs.get("animations_config", True),
        ),
    )
    app = _make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "no-color"
        assert not app.display_capabilities.color
        assert app.display_capabilities.term == "xterm-256color"
