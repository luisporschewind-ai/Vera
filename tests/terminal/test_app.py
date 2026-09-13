from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.compatibility import (
    current_compatibility_manifest,
    encode_compatibility_manifest,
)
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.session.actions import (
    ClearQueuedPrompt,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
)
from vera.session.controller import SessionController
from vera.terminal.app import VeraTerminalApp
from vera.terminal.widgets.composer import PromptSubmitted
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


def test_tui_app_is_not_a_public_contract(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake")
    dumped = encode_compatibility_manifest(current_compatibility_manifest())
    assert type(app).__name__ not in dumped
    assert app.controller is controller


@pytest.mark.asyncio
async def test_app_queues_only_when_run_active_and_not_approving(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        captured: list[object] = []
        app.bridge.submit = captured.append  # type: ignore[method-assign]
        controller.mark_active("run_1")
        app.on_prompt_submitted(PromptSubmitted("later"))
        assert captured == [QueuePrompt(text="later")]
        captured.clear()
        controller.queued_prompt = "later"
        app.on_prompt_submitted(PromptSubmitted("other"))
        assert captured == []
        assert app.query_one("#composer").text == "other"
        captured.clear()
        controller.queued_prompt = None
        controller._pending_approval = EventEnvelope(
            event_id="e1",
            run_id="run_1",
            sequence=1,
            timestamp=datetime.now(UTC),
            type="approval.required",
            payload={"approval_id": "a1"},
        )
        app.on_prompt_submitted(PromptSubmitted("during approval"))
        assert captured == []
        assert "during approval" in app.query_one("#composer").text


@pytest.mark.asyncio
async def test_app_clear_queue_and_editor_bindings(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        captured: list[object] = []
        app.bridge.submit = captured.append  # type: ignore[method-assign]
        controller.queued_prompt = "later"
        app.action_clear_composer_or_queue()
        assert captured == [ClearQueuedPrompt()]
        captured.clear()
        app.query_one("#composer").load_text("draft")
        app.action_open_editor()
        assert captured == [OpenExternalEditor(text="draft")]


@pytest.mark.asyncio
async def test_app_renders_help_and_doctor_as_display_only(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        for raw in ("/help", "/doctor"):
            for item in controller.dispatch(ExecuteSlashCommand(raw=raw)):
                if isinstance(item, EventEnvelope):
                    timeline.apply(app.projector.apply(item))
        await pilot.pause()
        help_event = next(
            item
            for item in controller.dispatch(ExecuteSlashCommand(raw="/help"))
            if isinstance(item, EventEnvelope) and item.type == "session.help"
        )
        doctor_event = next(
            item
            for item in controller.dispatch(ExecuteSlashCommand(raw="/doctor"))
            if isinstance(item, EventEnvelope) and item.type == "session.doctor"
        )
        help_block = app.projector.apply(help_event)[0].block  # type: ignore[union-attr]
        doctor_block = app.projector.apply(doctor_event)[0].block  # type: ignore[union-attr]
        assert help_block.kind.value == "status"
        assert "/doctor" in help_block.body or "开始" in help_block.body
        assert doctor_block.kind.value == "status"
        assert "version" in doctor_block.body
