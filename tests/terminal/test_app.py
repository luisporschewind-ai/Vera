from datetime import UTC, datetime
from pathlib import Path
from subprocess import CompletedProcess

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
from vera.terminal.app import VeraTerminalApp, _mention_prefix
from vera.terminal.bridge import RuntimeOutputReceived
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
        composer = app.query_one("#composer")
        assert composer.text == "other"
        assert composer.cursor_location == (0, len("other"))
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


def test_copy_to_clipboard_uses_pbcopy_on_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: object, **kwargs: object) -> CompletedProcess[bytes]:
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        return CompletedProcess(argv, 0)  # type: ignore[arg-type]

    monkeypatch.setattr("vera.terminal.app.sys.platform", "darwin")
    monkeypatch.setattr("vera.terminal.app.subprocess.run", fake_run)
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    app.copy_to_clipboard("任务失败：达到上限")
    assert captured["argv"] == ["/usr/bin/pbcopy"]
    assert captured["input"] == "任务失败：达到上限".encode()


@pytest.mark.asyncio
async def test_drag_selection_copies_via_pbcopy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: object, **kwargs: object) -> CompletedProcess[bytes]:
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        return CompletedProcess(argv, 0)  # type: ignore[arg-type]

    monkeypatch.setattr("vera.terminal.app.sys.platform", "darwin")
    monkeypatch.setattr("vera.terminal.app.subprocess.run", fake_run)
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        app.screen.get_selected_text = lambda: "选中的回答"  # type: ignore[method-assign]
        app.on_text_selected()
    assert captured["argv"] == ["/usr/bin/pbcopy"]
    assert captured["input"] == "选中的回答".encode()


@pytest.mark.asyncio
async def test_copy_without_selection_copies_latest_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: object, **kwargs: object) -> CompletedProcess[bytes]:
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        return CompletedProcess(argv, 0)  # type: ignore[arg-type]

    monkeypatch.setattr("vera.terminal.app.sys.platform", "darwin")
    monkeypatch.setattr("vera.terminal.app.subprocess.run", fake_run)
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        app.append_output(
            EventEnvelope(
                event_id="e1",
                run_id="run_1",
                sequence=1,
                timestamp=datetime.now(UTC),
                type="changeset.proposed",
                payload={
                    "files": [
                        {
                            "path": "notes.md",
                            "unified_diff": "--- a/notes.md\n+++ b/notes.md\n+hello-walk\n",
                        }
                    ]
                },
            )
        )
        app.screen.get_selected_text = lambda: ""  # type: ignore[method-assign]
        app.action_copy_text()
    assert captured["argv"] == ["/usr/bin/pbcopy"]
    assert b"hello-walk" in captured["input"]  # type: ignore[operator]
    assert b"\x1b" not in captured["input"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_slash_exit_leaves_tui(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        for item in controller.dispatch(ExecuteSlashCommand(raw="/exit")):
            if isinstance(item, EventEnvelope):
                app.on_runtime_output_received(RuntimeOutputReceived(item))
        await pilot.pause()
    assert app.return_value == 0 or not app.is_running
    assert controller.exit_requested


def test_mention_prefix_closes_after_completed_path() -> None:
    assert _mention_prefix("@") == ""
    assert _mention_prefix("@View") == "View"
    assert _mention_prefix("看 @ViewController.swift ") is None
    assert _mention_prefix("hello") is None
    assert _mention_prefix("@a\nb") is None


@pytest.mark.asyncio
async def test_submit_returns_to_tail_and_keeps_composer_focus(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        composer = app.query_one("#composer")
        timeline.mark_user_scrolled()
        timeline.focus()
        await pilot.pause()
        assert composer.has_focus is False
        app.on_prompt_submitted(PromptSubmitted("hello"))
        await pilot.pause()
        assert timeline.follow_tail is True
        assert composer.has_focus is True


@pytest.mark.asyncio
async def test_printable_key_returns_focus_to_composer(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        timeline = app.query_one("#timeline")
        composer = app.query_one("#composer")
        timeline.focus()
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert composer.has_focus is True
        assert "x" in composer.text


@pytest.mark.asyncio
async def test_app_mouse_scroll_is_consumed(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)

    class _Event:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    async with app.run_test(size=(80, 24)):
        up = _Event()
        down = _Event()
        app.on_mouse_scroll_up(up)
        app.on_mouse_scroll_down(down)
        assert up.stopped is True
        assert down.stopped is True


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
        assert "pass" in doctor_block.body
        config_event = next(
            item
            for item in controller.dispatch(ExecuteSlashCommand(raw="/config"))
            if isinstance(item, EventEnvelope) and item.type == "session.config"
        )
        config_block = app.projector.apply(config_event)[0].block  # type: ignore[union-attr]
        assert "来源" in config_block.body
        assert "sources:" not in config_block.body


@pytest.mark.asyncio
async def test_clear_wipes_timeline_and_new_keeps_history(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        app.append_output(
            EventEnvelope(
                event_id="e1",
                run_id="run_1",
                sequence=1,
                timestamp=datetime.now(UTC),
                type="assistant.message",
                payload={"text": "旧对话"},
            )
        )
        await pilot.pause()
        timeline = app.query_one("#timeline")
        assert timeline.widget_count() >= 1
        kept = timeline.widget_count()
        for item in controller.dispatch(ExecuteSlashCommand(raw="/new")):
            if isinstance(item, EventEnvelope):
                app.on_runtime_output_received(RuntimeOutputReceived(item))
        await pilot.pause()
        assert controller.conversation.snapshot() == ()
        assert timeline.widget_count() >= kept
        assert any("已开始新会话" in block.body for block in app.projector.blocks())
        for item in controller.dispatch(ExecuteSlashCommand(raw="/clear")):
            if isinstance(item, EventEnvelope):
                app.on_runtime_output_received(RuntimeOutputReceived(item))
        await pilot.pause()
        assert controller.conversation.snapshot() == ()
        blocks = app.projector.blocks()
        assert blocks
        assert "Model" in blocks[0].body
        assert "Workspace" in blocks[0].body
        assert any("已清空显示" in block.body for block in blocks)
        assert "旧对话" not in " ".join(block.body for block in blocks)
        assert timeline.follow_tail is False
        assert timeline.widget_count() >= 1


@pytest.mark.asyncio
async def test_app_bootstraps_recovery_hint(tmp_path: Path) -> None:
    from tests.recovery.helpers import make_snapshot
    from vera.persistence.journal import EventJournal
    from vera.persistence.recovery_snapshot import RecoverySnapshotStore
    from vera.redaction import Redactor
    from vera.terminal.widgets.blocks import TimelineBlockWidget

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("before\n", encoding="utf-8")
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
        FakeModelAdapter([]),
        ToolRegistry(),
        state_dir,
        snapshot_store=RecoverySnapshotStore(state_dir),
        installation_id="install-1",
    )
    journal = EventJournal(state_dir, "run_crash", Redactor([]))
    journal.append(
        "run.started",
        {
            "goal": "edit",
            "workspace_root": str(workspace),
            "model_profile": "fake",
            "kind": "task",
        },
    )
    RecoverySnapshotStore(state_dir).save(
        make_snapshot(workspace).model_copy(update={"run_id": "run_crash"})
    )
    controller = SessionController(
        RuntimeDependencies(runtime=runtime, config=config),
        workspace,
        "fake",
    )
    app = VeraTerminalApp(controller, workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        bodies = [widget.block.body for widget in app.query(TimelineBlockWidget)]
        joined = "\n".join(bodies)
        assert "发现 1 个待恢复任务" in joined
        assert "/recover" in joined
        for output in controller.dispatch(ExecuteSlashCommand(raw="/recover")):
            if isinstance(output, EventEnvelope):
                app.on_runtime_output_received(RuntimeOutputReceived(output))
        recover_bodies = [widget.block.body for widget in app.query(TimelineBlockWidget)]
        recover_text = "\n".join(recover_bodies)
        assert "run-id：run_crash" in recover_text
        assert "原因未记录" not in recover_text
        assert "恢复未完成" not in recover_text
        assert app.activity.current.active is False
