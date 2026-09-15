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


def test_default_theme_uses_deep_blue_accent() -> None:
    default = next(theme for theme in VERA_THEMES if theme.name == "default")
    assert default.primary == "#1B4F8A"
    assert default.secondary == "#0F2C4C"
    assert default.accent == "#2A5F9E"
    assert default.warning == "#C4A35A"
    assert default.background == "#121212"
    assert default.surface == "#121212"
    high_contrast = next(theme for theme in VERA_THEMES if theme.name == "high-contrast")
    assert high_contrast.accent == "#ffff00"


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
        assert accent == "#2a5f9e"
        border = str(app.query_one("#composer-bar").styles.border)
        assert "round" in border.lower()
        assert "42, 95, 158" in border


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
        timeline_border = str(app.query_one("#timeline").styles.border).lower()
        assert "solid" in timeline_border
        assert "tall" not in timeline_border
        assert "255, 255, 255" in timeline_border
        for item in app.controller.dispatch(ExecuteSlashCommand(raw="/theme no-color")):
            app.on_runtime_output_received(RuntimeOutputReceived(item))
        await pilot.pause()
        assert app.theme == "no-color"
        border = str(app.query_one("#composer-bar").styles.border)
        assert "136, 136, 136" in border
        assert "theme-no-color" in app.classes
        assert "theme-high-contrast" not in app.classes
