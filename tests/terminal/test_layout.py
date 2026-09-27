from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.display import display_width
from vera.terminal.widgets.composer import ComposerBar, PromptComposer
from vera.terminal.widgets.header import VeraHeader
from vera.terminal.widgets.status_line import VeraStatusLine
from vera.tools.registry import ToolRegistry


def make_controller(tmp_path: Path) -> SessionController:
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
    return SessionController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )


@pytest.mark.asyncio
async def test_narrow_width_hides_secondary_header_fields(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake")
    async with app.run_test(size=(80, 24)) as pilot:
        header = app.query_one("#header")
        assert "Vera" in header.visible_text()
        assert "推理" in header.visible_text()
        await pilot.resize_terminal(70, 24)
        await pilot.pause()
        assert header.has_class("-narrow")
        assert "Vera" in header.visible_text()


@pytest.mark.asyncio
async def test_resize_preserves_composer_text(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake")
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", PromptComposer)
        composer.load_text("keep me")
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert composer.text == "keep me"
        await pilot.resize_terminal(59, 15)
        await pilot.pause()
        assert composer.text == "keep me"
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert composer.text == "keep me"
        assert composer.has_focus


@pytest.mark.asyncio
async def test_first_task_collapses_welcome_next_to_path(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        header = app.query_one(VeraHeader)
        assert "Vera  0.1.0" in header.visible_text()
        assert "\n" in header.visible_text()
        app._collapse_welcome()
        await pilot.pause()
        text = header.visible_text()
        assert text.startswith("VERA  ")
        assert "\n" not in text


@pytest.mark.asyncio
async def test_resize_keeps_footer_model_and_chrome_inside_screen(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        footer = app.query_one("#status-line", VeraStatusLine)
        text = str(footer.render())
        assert "fake-model" in text
        assert "推理" in text
        assert display_width(text) <= max(int(footer.size.width), 4)
        assert footer.region.right <= app.size.width
        bar = app.query_one("#composer-bar", ComposerBar)
        assert bar.region.right <= app.size.width
        assert bar.region.x >= 0
        header = app.query_one("#header")
        assert header.region.right <= app.size.width


@pytest.mark.asyncio
async def test_resize_burst_does_not_clear_each_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(120, 40)) as pilot:
        driver = app._driver
        assert driver is not None
        writes: list[str] = []
        monkeypatch.setattr(driver, "write", writes.append)

        await pilot.resize_terminal(100, 32)
        await pilot.resize_terminal(90, 28)
        await pilot.resize_terminal(80, 24)

        assert "\x1b[2J\x1b[H" not in "".join(writes)

        await pilot.pause(0.6)
        clears = [write for write in writes if "\x1b[2J\x1b[H" in write]
        assert len(clears) == 1
        assert "Vera" in clears[0]
