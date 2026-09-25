import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.skills.test_manifest import write_skill
from tests.terminal.test_app import make_controller
from vera.contracts.events import EventEnvelope
from vera.session.actions import ExecuteSlashCommand, SubmitPrompt
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService
from vera.terminal.app import VeraTerminalApp
from vera.terminal.bridge import RuntimeOutputReceived, WorkerStopped
from vera.terminal.widgets.composer import PromptComposer, PromptSubmitted
from vera.terminal.widgets.skill_picker import SkillPicker
from vera.terminal.widgets.status_line import VeraStatusLine


def _controller_with_skill(tmp_path: Path):
    controller = make_controller(tmp_path)
    user = tmp_path / "user"
    user.mkdir()
    write_skill(user)
    controller.dependencies.runtime.skill_selection_service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )
    return controller


def _skill_event(controller, raw: str, event_type: str) -> EventEnvelope:
    return next(
        item
        for item in controller.dispatch(ExecuteSlashCommand(raw=raw))
        if isinstance(item, EventEnvelope) and item.type == event_type
    )


class _RecordingSubmit:
    def __init__(self) -> None:
        self.actions: list[object] = []

    def __call__(self, action: object) -> str:
        self.actions.append(action)
        return self.last_request_id

    @property
    def last_request_id(self) -> str:
        return f"request-{len(self.actions)}"


def _deliver_list(app: VeraTerminalApp, controller, recorder: _RecordingSubmit) -> EventEnvelope:
    app.bridge.submit = recorder  # type: ignore[method-assign]
    app.on_prompt_submitted(PromptSubmitted("/skills"))
    listed = _skill_event(controller, "/skills", "skill.listed")
    app.on_runtime_output_received(
        RuntimeOutputReceived(listed, request_id=recorder.last_request_id)
    )
    return listed


@pytest.mark.asyncio
async def test_skills_list_enter_selects_once_without_submitting_draft(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one(PromptComposer)
        composer.load_text("draft question")
        composer.cursor_location = (0, 5)
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        assert picker.display

        await pilot.press("enter", "enter")
        await pilot.pause()
        assert recorder.actions == [
            ExecuteSlashCommand(raw="/skills"),
            ExecuteSlashCommand(raw="/skills use user:python-review"),
        ]
        assert not any(isinstance(item, SubmitPrompt) for item in recorder.actions)
        assert composer.text == "draft question"
        assert composer.cursor_location == (0, 5)

        changed = _skill_event(
            controller, "/skills use user:python-review", "skill.selection.changed"
        )
        app.on_runtime_output_received(
            RuntimeOutputReceived(changed, request_id=recorder.last_request_id)
        )
        await pilot.pause()
        assert not picker.display
        assert composer.has_focus
        assert composer.text == "draft question"
        assert composer.cursor_location == (0, 5)
        assert controller.snapshot().skill_selection.skill_id == "user:python-review"


@pytest.mark.asyncio
async def test_picker_resize_and_printable_keys_keep_focus_and_draft(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one(PromptComposer)
        composer.load_text("draft")
        composer.cursor_location = (0, 2)
        _deliver_list(app, controller, _RecordingSubmit())
        picker = app.query_one(SkillPicker)
        await pilot.pause()
        assert picker.query_one("#skill-picker-options").has_focus

        await pilot.resize_terminal(60, 16)
        await pilot.pause()
        assert picker.query_one("#skill-picker-options").has_focus
        await pilot.press("x")
        assert composer.text == "draft"
        assert composer.cursor_location == (0, 2)
        assert picker.display


@pytest.mark.asyncio
async def test_picker_escape_does_not_change_selection_and_pending_escape_waits(
    tmp_path: Path,
) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        await pilot.press("escape")
        assert not picker.display
        assert controller.snapshot().skill_selection.mode == "none"
        _deliver_list(app, controller, recorder)
        await pilot.press("enter", "escape")
        assert picker.display
        assert picker.pending_skill_id == "user:python-review"
        assert recorder.actions[-1] == ExecuteSlashCommand(raw="/skills use user:python-review")


@pytest.mark.asyncio
async def test_picker_does_not_open_during_run_or_approval(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        recorder = _RecordingSubmit()
        picker = app.query_one(SkillPicker)
        listed = _skill_event(controller, "/skills", "skill.listed")
        app.bridge.submit = recorder  # type: ignore[method-assign]
        controller.mark_active("run_1")
        app.on_prompt_submitted(PromptSubmitted("/skills"))
        app.on_runtime_output_received(
            RuntimeOutputReceived(listed, request_id=recorder.last_request_id)
        )
        assert not picker.display
        controller._active_run_id = None
        controller._pending_approval = EventEnvelope(
            event_id="e1",
            run_id="run_1",
            sequence=1,
            timestamp=datetime.now(UTC),
            type="approval.required",
            payload={"approval_id": "a1"},
        )
        app.on_prompt_submitted(PromptSubmitted("/skills"))
        app.on_runtime_output_received(
            RuntimeOutputReceived(listed, request_id=recorder.last_request_id)
        )
        assert not picker.display


@pytest.mark.asyncio
async def test_picker_worker_failure_closes_with_error(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        await pilot.press("enter")
        assert picker.pending_skill_id == "user:python-review"
        app.on_worker_stopped(
            WorkerStopped(
                None,
                "worker_failed:dispatch_failed",
                request_id=recorder.last_request_id,
            )
        )
        assert not picker.display
        assert "失败" in app.query_one(VeraStatusLine)._notice


@pytest.mark.asyncio
async def test_picker_worker_completion_without_selection_confirmation_fails_closed(
    tmp_path: Path,
) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        await pilot.press("enter")
        assert picker.pending_skill_id == "user:python-review"
        app.on_worker_stopped(WorkerStopped(None, "completed", request_id="request-1"))
        assert picker.display
        app.on_worker_stopped(
            WorkerStopped(
                None,
                "completed",
                request_id=recorder.last_request_id,
            )
        )
        assert not picker.display
        assert "确认" in app.query_one(VeraStatusLine)._notice


@pytest.mark.asyncio
async def test_picker_rejects_deleted_source_without_false_success(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        await pilot.press("enter")
        shutil.rmtree(tmp_path / "user" / "python-review")
        rejected = _skill_event(
            controller, "/skills use user:python-review", "skill.selection.changed"
        )
        app.on_runtime_output_received(
            RuntimeOutputReceived(rejected, request_id=recorder.last_request_id)
        )
        assert picker.display
        assert picker.pending_skill_id is None
        assert "skill_not_found" in picker.error_text


@pytest.mark.asyncio
async def test_picker_shows_core_version_after_source_change(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        await pilot.press("enter")
        manifest = tmp_path / "user" / "python-review" / "skill.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace('version = "1.0.0"', 'version = "2.0.0"'),
            encoding="utf-8",
        )
        changed = _skill_event(
            controller, "/skills use user:python-review", "skill.selection.changed"
        )
        assert changed.payload["selection"]["version"] == "2.0.0"
        app.on_runtime_output_received(
            RuntimeOutputReceived(changed, request_id=recorder.last_request_id)
        )
        assert not app.query_one(SkillPicker).display
        assert "2.0.0" in app.query_one(VeraStatusLine)._notice


@pytest.mark.asyncio
async def test_only_exact_skills_command_opens_picker(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        recorder = _RecordingSubmit()
        app.bridge.submit = recorder  # type: ignore[method-assign]
        app.on_prompt_submitted(PromptSubmitted("/skills list"))
        alias_listed = _skill_event(controller, "/skills list", "skill.listed")
        app.on_runtime_output_received(
            RuntimeOutputReceived(alias_listed, request_id=recorder.last_request_id)
        )
        assert not app.query_one(SkillPicker).display
        app.on_prompt_submitted(PromptSubmitted("/skills"))
        listed = _skill_event(controller, "/skills", "skill.listed")
        app.on_runtime_output_received(
            RuntimeOutputReceived(listed, request_id=recorder.last_request_id)
        )
        assert app.query_one(SkillPicker).display


@pytest.mark.asyncio
async def test_picker_disables_duplicate_ids_and_handles_bad_list_payload(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    shutil.copytree(tmp_path / "user" / "python-review", tmp_path / "user" / "duplicate")
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(60, 16)) as pilot:
        recorder = _RecordingSubmit()
        listed = _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        assert picker.display
        before = len(recorder.actions)
        await pilot.press("enter")
        assert len(recorder.actions) == before

        app.on_prompt_submitted(PromptSubmitted("/skills"))
        malformed = listed.model_copy(update={"payload": {"items": "not-a-list"}})
        app.on_runtime_output_received(
            RuntimeOutputReceived(malformed, request_id=recorder.last_request_id)
        )
        assert not picker.display
        assert "无效" in app.query_one(VeraStatusLine)._notice


@pytest.mark.asyncio
@pytest.mark.parametrize("theme", ["default", "light", "cream", "high-contrast", "no-color"])
async def test_picker_theme_and_resize_keep_text_cursor(tmp_path: Path, theme: str) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(60, 16)) as pilot:
        app._apply_theme(theme)
        _deliver_list(app, controller, _RecordingSubmit())
        picker = app.query_one(SkillPicker)
        await pilot.pause()
        options = picker.query_one("#skill-picker-options")
        assert str(options.get_option_at_index(1).prompt).startswith("› ")
        assert picker.region.y + picker.region.height <= app.query_one("#composer-bar").region.y
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert picker.display
        assert options.has_focus
        assert str(options.get_option_at_index(1).prompt).startswith("› ")


@pytest.mark.asyncio
async def test_real_bridge_lists_and_selects_without_starting_run(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        app.on_prompt_submitted(PromptSubmitted("/skills"))
        await pilot.pause(0.1)
        picker = app.query_one(SkillPicker)
        assert picker.display
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert not picker.display
        assert controller.snapshot().skill_selection.skill_id == "user:python-review"
        assert controller.active_run_id is None
        assert not any(block.kind.value == "assistant" for block in app.projector.blocks())

        prompt_outputs = tuple(controller.dispatch(SubmitPrompt(text="review")))
        assert any(
            isinstance(item, EventEnvelope) and item.type == "skill.snapshot.bound"
            for item in prompt_outputs
        )
        assert controller.snapshot().skill_selection.mode == "none"


@pytest.mark.asyncio
async def test_footer_skill_notice_follows_core_selection(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        status = app.query_one(VeraStatusLine)

        def deliver(event: EventEnvelope) -> None:
            app.on_runtime_output_received(RuntimeOutputReceived(event, request_id="typed"))

        deliver(
            _skill_event(controller, "/skills use user:python-review", "skill.selection.changed")
        )
        assert status.notice.startswith("已选择 user:python-review · 1.0.0")

        deliver(_skill_event(controller, "/skills clear", "skill.selection.changed"))
        assert status.notice == ""

        deliver(
            _skill_event(controller, "/skills use user:python-review", "skill.selection.changed")
        )
        prompt_outputs = tuple(controller.dispatch(SubmitPrompt(text="review")))
        bound = next(
            item
            for item in prompt_outputs
            if isinstance(item, EventEnvelope) and item.type == "skill.selection.changed"
        )
        assert bound.payload["selection"]["mode"] == "none"
        deliver(bound)
        assert status.notice == ""

        status.set_status("已复制选中文本")
        deliver(_skill_event(controller, "/skills clear", "skill.selection.changed"))
        assert status.notice == "已复制选中文本"


@pytest.mark.asyncio
async def test_interleaved_list_events_open_only_latest_exact_request(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)):
        actions: list[object] = []

        def record(action: object) -> str:
            actions.append(action)
            return f"request-{len(actions)}"

        app.bridge.submit = record  # type: ignore[method-assign]
        app.on_prompt_submitted(PromptSubmitted("/skills list"))
        app.on_prompt_submitted(PromptSubmitted("/skills"))
        old = _skill_event(controller, "/skills list", "skill.listed")
        app.on_runtime_output_received(RuntimeOutputReceived(old, request_id="request-1"))
        assert not app.query_one(SkillPicker).display
        current = _skill_event(controller, "/skills", "skill.listed")
        app.on_runtime_output_received(RuntimeOutputReceived(current, request_id="request-2"))
        assert app.query_one(SkillPicker).display
        assert actions == [
            ExecuteSlashCommand(raw="/skills list"),
            ExecuteSlashCommand(raw="/skills"),
        ]


@pytest.mark.asyncio
async def test_stale_same_skill_confirmation_cannot_complete_new_picker(
    tmp_path: Path,
) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        actions: list[object] = []

        def record(action: object) -> str:
            actions.append(action)
            return f"request-{len(actions)}"

        app.bridge.submit = record  # type: ignore[method-assign]
        app.on_prompt_submitted(PromptSubmitted("/skills"))
        listed = _skill_event(controller, "/skills", "skill.listed")
        app.on_runtime_output_received(RuntimeOutputReceived(listed, request_id="request-1"))
        picker = app.query_one(SkillPicker)
        await pilot.press("enter")
        assert picker.pending_skill_id == "user:python-review"

        selected = _skill_event(
            controller, "/skills use user:python-review", "skill.selection.changed"
        )
        app.on_runtime_output_received(
            RuntimeOutputReceived(selected, request_id="previous-request")
        )
        assert picker.display
        assert picker.pending_skill_id == "user:python-review"
        app.on_runtime_output_received(RuntimeOutputReceived(selected, request_id="request-2"))
        assert not picker.display
        assert actions == [
            ExecuteSlashCommand(raw="/skills"),
            ExecuteSlashCommand(raw="/skills use user:python-review"),
        ]


@pytest.mark.asyncio
async def test_skill_picker_hides_and_blocks_slash_completions(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one(PromptComposer)
        from vera.terminal.widgets.completions import CompletionList

        completions = app.query_one(CompletionList)
        composer.load_text("/")
        app._refresh_completions("/")
        assert completions.display

        _deliver_list(app, controller, _RecordingSubmit())
        picker = app.query_one(SkillPicker)
        assert picker.display
        assert not completions.display

        composer.focus()
        composer.load_text("/st")
        app._refresh_completions("/st")
        assert picker.display
        assert not completions.display
        assert composer._slash_completions() is None

        await pilot.press("escape")
        await pilot.pause()
        assert not picker.display
        assert composer.has_focus

        composer.load_text("/st")
        app._refresh_completions("/st")
        assert completions.display
        assert not picker.display


@pytest.mark.asyncio
async def test_other_slash_command_closes_idle_skill_picker(tmp_path: Path) -> None:
    controller = _controller_with_skill(tmp_path)
    app = VeraTerminalApp(controller, controller.workspace, "fake", animations=False)
    async with app.run_test(size=(80, 24)) as pilot:
        recorder = _RecordingSubmit()
        _deliver_list(app, controller, recorder)
        picker = app.query_one(SkillPicker)
        assert picker.display

        app.on_prompt_submitted(PromptSubmitted("/status"))
        await pilot.pause()
        assert not picker.display
        assert recorder.actions[-1] == ExecuteSlashCommand(raw="/status")
