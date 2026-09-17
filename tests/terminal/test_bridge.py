import asyncio
import threading
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import SessionAction, SubmitPrompt
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.tools.registry import ToolRegistry


class BlockingController(SessionController):
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._started = threading.Event()
        self._release = threading.Event()

    async def wait_until_started(self, pilot, timeout: float = 2.0) -> None:  # type: ignore[no-untyped-def]
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self._started.is_set():
                return
            await pilot.pause()
        raise AssertionError("worker did not start")

    def release(self) -> None:
        self._release.set()

    def dispatch(self, action: SessionAction):  # type: ignore[override]
        del action
        self._started.set()
        self._release.wait(timeout=2.0)
        yield self._session_event("run.completed", {"state": "completed"})


def make_blocking_app(tmp_path: Path) -> tuple[VeraTerminalApp, BlockingController]:
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
    controller = BlockingController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    return VeraTerminalApp(controller, workspace, "fake"), controller


@pytest.mark.asyncio
async def test_slow_runtime_does_not_block_composer(tmp_path: Path) -> None:
    app, controller = make_blocking_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer")
        composer.load_text("hi")
        app.submit_composer()
        await controller.wait_until_started(pilot)
        assert composer.disabled is False
        composer.load_text("still typing")
        assert composer.text == "still typing"
        controller.release()
        await pilot.pause()
        assert app.received_sequences == sorted(app.received_sequences)


@pytest.mark.asyncio
async def test_worker_exception_does_not_crash_app(tmp_path: Path) -> None:
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

    class FailingController(SessionController):
        def dispatch(self, action: SessionAction):  # type: ignore[override]
            del action
            raise RuntimeError("boom-secret")
            yield  # pragma: no cover

    controller = FailingController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    app = VeraTerminalApp(controller, workspace, "fake")
    async with app.run_test(size=(80, 24)) as pilot:
        app.bridge.submit(SubmitPrompt(text="x"))
        for _ in range(20):
            status = str(app.query_one("#work-rail").render())
            if "Worker 失败" in status:
                break
            await pilot.pause()
        assert "Worker 失败" in str(app.query_one("#work-rail").render())
        assert "boom-secret" not in str(app.query_one("#work-rail").render())
        assert "boom-secret" not in str(app.query_one("#status-line").render())


@pytest.mark.asyncio
async def test_stream_order_preserved(tmp_path: Path) -> None:
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
    runtime = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="ok", finish_reason="stop")]),
        ToolRegistry(),
        state_dir,
    )
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    app = VeraTerminalApp(controller, workspace, "fake")
    async with app.run_test(size=(80, 24)) as pilot:
        app.bridge.submit(SubmitPrompt(text="hello"))
        for _ in range(30):
            if app.received_sequences:
                break
            await pilot.pause()
        assert app.received_sequences
        assert app.received_sequences == sorted(app.received_sequences)
