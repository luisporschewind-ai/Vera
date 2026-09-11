from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
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
async def test_app_mounts_stable_regions(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake")
    async with app.run_test(size=(80, 24)) as pilot:
        assert app.query_one("#timeline")
        assert app.query_one("#composer").has_focus
        await pilot.resize_terminal(59, 15)
        await pilot.pause()
        assert app.query_one("#terminal-too-small").display is True
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert app.query_one("#composer").has_focus
        assert app.query_one("#terminal-too-small").display is False


@pytest.mark.asyncio
async def test_app_accepts_minimum_and_large_sizes(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake")
    async with app.run_test(size=(60, 16)) as pilot:
        assert app.query_one("#terminal-too-small").display is False
        await pilot.resize_terminal(120, 40)
        assert app.query_one("#composer").has_focus
