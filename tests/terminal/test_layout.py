from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.composer import PromptComposer
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
        assert str(controller.workspace) in str(header.render())
        await pilot.resize_terminal(70, 24)
        await pilot.pause()
        assert header.has_class("-narrow")
        assert str(controller.workspace) not in str(header.render())


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
