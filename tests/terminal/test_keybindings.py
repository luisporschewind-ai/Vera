from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.actions import CancelActiveRun
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.tools.registry import ToolRegistry


class RecordingController(SessionController):
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.actions: list[object] = []

    def dispatch(self, action):  # type: ignore[no-untyped-def, override]
        self.actions.append(action)
        if False:  # pragma: no cover
            yield


def make_app(tmp_path: Path) -> tuple[VeraTerminalApp, RecordingController]:
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
    controller = RecordingController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake", animations=False), controller


@pytest.mark.asyncio
async def test_escape_cancels_active_run_but_does_not_exit(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    controller.mark_active("run_1")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert controller.actions[-1] == CancelActiveRun(run_id="run_1")
        assert app.is_running


@pytest.mark.asyncio
async def test_escape_does_not_clear_composer_when_idle(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer")
        composer.load_text("draft")
        await pilot.press("escape")
        await pilot.pause()
        assert composer.text == "draft"
        assert controller.actions == []


@pytest.mark.asyncio
async def test_ctrl_c_cancels_active_run_but_does_not_exit(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    controller.mark_active("run_1")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert controller.actions[-1] == CancelActiveRun(run_id="run_1")
        assert app.is_running


@pytest.mark.asyncio
async def test_ctrl_c_clears_composer_when_idle(tmp_path: Path) -> None:
    app, _controller = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer")
        composer.load_text("draft")
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert composer.text == ""


@pytest.mark.asyncio
async def test_ctrl_d_exits_only_when_idle_and_empty(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_exit_if_idle()
        await pilot.pause()
    assert any(type(action).__name__ == "CloseSession" for action in controller.actions)
    assert app.return_value == 0 or not app.is_running


@pytest.mark.asyncio
async def test_ctrl_d_ignored_when_composer_has_text(tmp_path: Path) -> None:
    app, controller = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one("#composer").load_text("keep")
        app.action_exit_if_idle()
        await pilot.pause()
        assert controller.actions == []
        assert app.is_running
