import errno
from pathlib import Path

from vera.bootstrap import RuntimeDependencies
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import ConversationTurn
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.session_store import ConversationSessionStore
from vera.runtime.engine import VeraRuntime
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.session.controller import SessionController
from vera.tools.registry import ToolRegistry


def make_controller(
    workspace: Path,
    turns: list[ModelTurn],
    *,
    editor_argv: tuple[str, ...] = (),
) -> SessionController:
    state_dir = workspace.parent / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(max_conversation_bytes=200_000),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
        editor_argv=editor_argv,
    )
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    deps = RuntimeDependencies(runtime=runtime, config=config)
    return SessionController(deps, workspace, "fake")


def proposal(call_id: str, content: str) -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id=call_id,
                name="propose_changeset",
                arguments={
                    "summary": "edit",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": content,
                        }
                    ],
                },
            ),
        ),
    )


def test_controller_submits_prompt_through_runtime(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(
        workspace,
        [ModelTurn(assistant_text="解释完成", finish_reason="stop")],
    )

    outputs = tuple(controller.dispatch(SubmitPrompt(text="解释这个项目")))

    prompt = next(
        item
        for item in outputs
        if isinstance(item, EventEnvelope) and item.type == "session.user_prompt"
    )
    assert prompt.payload["text"] == "解释这个项目"
    assert any(isinstance(item, EventEnvelope) and item.type == "run.completed" for item in outputs)
    assert controller.active_run_id is None


def test_controller_rejects_second_prompt_while_run_active(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    controller.mark_active("run_1")

    outputs = tuple(controller.dispatch(SubmitPrompt(text="second")))

    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "run_active"


def test_controller_pauses_on_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])

    outputs = tuple(controller.dispatch(SubmitPrompt(text="edit")))

    assert any(
        isinstance(item, EventEnvelope) and item.type == "approval.required" for item in outputs
    )
    assert controller.pending_approval_id is not None
    assert controller.active_run_id is not None


def test_cancel_is_idempotent_when_idle(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])

    outputs = tuple(controller.dispatch(CancelActiveRun(run_id="missing")))

    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "no_active_run"


def test_close_cancels_pending_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit")))
    assert controller.pending_approval_id is not None

    outputs = tuple(controller.dispatch(CloseSession()))

    assert any(isinstance(item, EventEnvelope) and item.type == "run.cancelled" for item in outputs)
    assert any(
        isinstance(item, EventEnvelope) and item.type == "session.closed" for item in outputs
    )
    assert controller.snapshot().closed is True
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_queue_prompt_waits_for_terminal_then_starts_new_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(
        workspace,
        [
            ModelTurn(assistant_text="first", finish_reason="stop"),
            ModelTurn(assistant_text="second", finish_reason="stop"),
        ],
    )
    controller.mark_active("run_1")

    queued = tuple(controller.dispatch(QueuePrompt(text="follow up")))
    assert queued[-1].type == "session.prompt_queued"
    assert controller.queued_prompt == "follow up"
    occupied = tuple(controller.dispatch(QueuePrompt(text="other")))
    assert occupied[-1].payload["reason_code"] == "queue_occupied"
    cleared = tuple(controller.dispatch(ClearQueuedPrompt()))
    assert cleared[-1].type == "session.prompt_queue_cleared"
    tuple(controller.dispatch(QueuePrompt(text="follow up")))

    controller._active_run_id = None
    outputs = tuple(controller.dispatch(SubmitPrompt(text="first")))
    types = [item.type for item in outputs if isinstance(item, EventEnvelope)]
    assert "run.completed" in types
    assert "session.prompt_queue_flushed" in types
    assert types.count("run.completed") == 2
    assert controller.queued_prompt is None
    assert controller.active_run_id is None


def test_queue_rejected_during_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit")))
    assert controller.pending_approval_id is not None

    outputs = tuple(controller.dispatch(QueuePrompt(text="next")))
    assert outputs[-1].type == "session.action_rejected"
    assert outputs[-1].payload["reason_code"] == "approval_pending"
    assert controller.queued_prompt is None


def test_close_clears_in_memory_history_and_queue(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    controller.mark_active("run_1")
    tuple(controller.dispatch(QueuePrompt(text="queued")))
    controller.history.record("remembered")
    tuple(controller.dispatch(CloseSession()))
    assert len(controller.history) == 0
    assert controller.queued_prompt is None


def test_external_editor_requires_preview_then_returns_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [], editor_argv=("/usr/bin/true",))
    preview = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert preview[-1].type == "session.editor_preview"
    assert preview[-1].payload["needs_confirmation"] is True
    tuple(controller.dispatch(ConfirmExternalEditor(accept=True)))
    closed = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert closed[-1].type == "session.editor_closed"
    assert closed[-1].payload["status"] == "unchanged"


def test_external_editor_rejects_unconfigured_argv(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    outputs = tuple(controller.dispatch(OpenExternalEditor(text="draft")))
    assert outputs[-1].payload["reason_code"] == "editor_unconfigured"


def test_new_slash_commands_are_structured_and_unknown_is_not_executed(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = make_controller(workspace, [])
    help_event = tuple(controller.dispatch(ExecuteSlashCommand(raw="/help")))[-1]
    assert help_event.type == "session.help"
    assert "代码与证据" in str(help_event.payload["text"])
    unknown = tuple(controller.dispatch(ExecuteSlashCommand(raw="/docotr")))[-1]
    assert unknown.type == "session.message"
    assert "/doctor" in str(unknown.payload.get("suggestions"))
    doctor = tuple(controller.dispatch(ExecuteSlashCommand(raw="/doctor")))[-1]
    assert doctor.type == "session.doctor"
    usage = tuple(controller.dispatch(ExecuteSlashCommand(raw="/usage")))[-1]
    assert usage.payload["calls"] == "unavailable"
    theme = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme high-contrast")))[-1]
    assert theme.payload["theme"] == "high-contrast"
    assert "当前主题：high-contrast" in str(theme.payload["text"])
    listed = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme")))[-1]
    assert listed.payload["theme"] == "high-contrast"
    unknown_theme = tuple(controller.dispatch(ExecuteSlashCommand(raw="/theme neon")))[-1]
    assert unknown_theme.type == "session.message"
    assert "未知主题" in str(unknown_theme.payload["text"])
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    assert diff.payload["files"] == []
    review = tuple(controller.dispatch(ExecuteSlashCommand(raw="/review")))[-1]
    assert review.type == "session.review"


def test_diff_after_completed_run_uses_last_changeset(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    started = tuple(controller.dispatch(SubmitPrompt(text="edit hello")))
    pending = next(
        item
        for item in started
        if isinstance(item, EventEnvelope) and item.type == "approval.required"
    )
    tuple(
        controller.dispatch(
            ResolveSessionApproval(
                approval_id=str(pending.payload["approval_id"]),
                decision="approve",
            )
        )
    )
    assert controller.active_run_id is None
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    files = diff.payload["files"]
    assert isinstance(files, list) and files
    assert files[0]["path"] == "hello.txt"
    text = str(diff.payload.get("text", ""))
    assert "hello.txt" in text
    assert "没有 Diff。" not in text
    assert diff.payload.get("applied") is True
    assert "未写入工作区" not in text


def test_diff_before_apply_is_labeled_unwritten(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    controller = make_controller(workspace, [proposal("c1", "new\n")])
    tuple(controller.dispatch(SubmitPrompt(text="edit hello")))
    diff = tuple(controller.dispatch(ExecuteSlashCommand(raw="/diff")))[-1]
    assert diff.type == "session.diff"
    assert diff.payload.get("applied") is False
    assert "未写入工作区" in str(diff.payload.get("text", ""))
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"


class RecordingSessionStore:
    def __init__(self, inner: ConversationSessionStore) -> None:
        self.inner = inner
        self.calls: list[str] = []
        self.fail_on: str | None = None

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)

    def create(self, workspace: Path):  # type: ignore[no-untyped-def]
        self.calls.append("create")
        if self.fail_on == "create":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.create(workspace)

    def append_turn(self, session_id: str, turn: ConversationTurn):  # type: ignore[no-untyped-def]
        self.calls.append("append_turn")
        if self.fail_on == "append_turn":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.append_turn(session_id, turn)

    def append_compaction(self, session_id: str, summary: str, through_sequence: int):  # type: ignore[no-untyped-def]
        self.calls.append("append_compaction")
        if self.fail_on == "append_compaction":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.append_compaction(session_id, summary, through_sequence)

    def close(self, session_id: str, reason: str):  # type: ignore[no-untyped-def]
        self.calls.append("close")
        if self.fail_on == "close":
            raise OSError(errno.ENOSPC, "No space left on device")
        return self.inner.close(session_id, reason)


def make_persistent_controller(
    workspace: Path,
    turns: list[ModelTurn],
    *,
    store: RecordingSessionStore | None = None,
    loaded_session=None,
    source=None,
) -> tuple[SessionController, RecordingSessionStore]:
    state_dir = workspace.parent / "state"
    config = VeraConfig(
        state_dir=state_dir,
        limits=Limits(max_conversation_bytes=200_000),
        providers={
            "fake": ProviderConfig(
                base_url="https://example.invalid",
                model="fake-model",
                api_key_env="FAKE_API_KEY",
            )
        },
    )
    runtime = VeraRuntime(FakeModelAdapter(turns), ToolRegistry(), state_dir)
    deps = RuntimeDependencies(runtime=runtime, config=config, installation_id="install-test")
    inner = ConversationSessionStore(state_dir, "install-test")
    wrapped = store or RecordingSessionStore(inner)
    controller = SessionController(
        deps,
        workspace,
        "fake",
        session_store=wrapped,
        loaded_session=loaded_session,
        source=source,
    )
    return controller, wrapped


def test_append_turn_happens_before_commit_turn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    order: list[str] = []
    controller, store = make_persistent_controller(
        workspace, [ModelTurn(assistant_text="你好", finish_reason="stop")]
    )
    original_append = store.append_turn
    original_commit = controller.conversation.commit_turn

    def append_turn(session_id: str, turn: ConversationTurn):  # type: ignore[no-untyped-def]
        order.append("append_turn")
        return original_append(session_id, turn)

    def commit_turn(turn: ConversationTurn) -> None:
        order.append("commit_turn")
        original_commit(turn)

    store.append_turn = append_turn  # type: ignore[method-assign]
    controller.conversation.commit_turn = commit_turn  # type: ignore[method-assign]
    tuple(controller.dispatch(SubmitPrompt(text="Hello")))
    assert order[:2] == ["append_turn", "commit_turn"]


def test_failed_append_keeps_run_result_and_marks_unsaved(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller, store = make_persistent_controller(
        workspace, [ModelTurn(assistant_text="你好", finish_reason="stop")]
    )
    store.fail_on = "append_turn"
    outputs = tuple(controller.dispatch(SubmitPrompt(text="Hello")))
    assert any(item.type == "run.completed" for item in outputs if isinstance(item, EventEnvelope))
    changed = next(
        item
        for item in outputs
        if isinstance(item, EventEnvelope) and item.type == "session.persistence_changed"
    )
    assert changed.payload["state"] == "unsaved"
    assert changed.payload["error_code"] == "no_space"
    assert "advice" in changed.payload
    assert "/tmp" not in str(changed.payload)
    stats = next(
        item
        for item in tuple(controller.dispatch(ExecuteSlashCommand(raw="/status")))
        if isinstance(item, EventEnvelope) and item.type == "session.status"
    )
    assert stats.payload["context"]["persistent_state"] == "unsaved"
    assert controller.conversation.snapshot()[-1].content == "你好"
    loaded = store.inner.load(controller.snapshot().session_id, workspace)
    assert loaded.model_messages == ()
    closed = tuple(controller.dispatch(CloseSession()))
    assert any(
        item.type == "session.close_warning" for item in closed if isinstance(item, EventEnvelope)
    )


def test_later_success_does_not_clear_unsaved(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller, store = make_persistent_controller(
        workspace,
        [
            ModelTurn(assistant_text="first", finish_reason="stop"),
            ModelTurn(assistant_text="second", finish_reason="stop"),
        ],
    )
    store.fail_on = "append_turn"
    tuple(controller.dispatch(SubmitPrompt(text="one")))
    store.fail_on = None
    tuple(controller.dispatch(SubmitPrompt(text="two")))
    status = tuple(controller.dispatch(ExecuteSlashCommand(raw="/status")))[-1]
    assert status.payload["context"]["persistent_state"] == "unsaved"


def test_restart_after_saved_turn_restores_once(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first, store = make_persistent_controller(
        workspace, [ModelTurn(assistant_text="你好", finish_reason="stop")]
    )
    tuple(first.dispatch(SubmitPrompt(text="Hello")))
    session_id = first.snapshot().session_id
    loaded = store.inner.load(session_id, workspace)
    second, _ = make_persistent_controller(
        workspace,
        [ModelTurn(assistant_text="继续", finish_reason="stop")],
        store=store,
        loaded_session=loaded,
        source="resumed",
    )
    assert [item.content for item in second.conversation.snapshot()] == ["Hello", "你好"]
    assert second.history.search("Hello") == ("Hello",)
    assert second._conversation_stats().source == "resumed"
    assert second._conversation_stats().persistent_state == "saved"
    reloaded = store.inner.load(session_id, workspace)
    assert len([item for item in reloaded.records if item.type == "turn.committed"]) == 1


def test_compact_persists_before_replacing_context(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller, store = make_persistent_controller(
        workspace,
        [
            ModelTurn(assistant_text="hello", finish_reason="stop"),
            ModelTurn(assistant_text="保留结论：继续。", finish_reason="stop"),
            ModelTurn(assistant_text="保留结论：继续。", finish_reason="stop"),
        ],
    )
    tuple(controller.dispatch(SubmitPrompt(text="Hello")))
    before = controller.conversation.snapshot()
    store.fail_on = "append_compaction"
    outputs = tuple(controller.dispatch(ExecuteSlashCommand(raw="/compact")))
    assert controller.conversation.snapshot() == before
    assert any(
        item.type == "session.persistence_changed"
        for item in outputs
        if isinstance(item, EventEnvelope)
    )
    store.fail_on = None
    tuple(controller.dispatch(ExecuteSlashCommand(raw="/compact")))
    assert store.calls.count("append_compaction") == 2
    assert controller.conversation.snapshot()[0].role == "summary"


def test_new_and_clear_create_new_persistent_sessions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller, store = make_persistent_controller(
        workspace,
        [
            ModelTurn(assistant_text="first", finish_reason="stop"),
            ModelTurn(assistant_text="second", finish_reason="stop"),
        ],
    )
    tuple(controller.dispatch(SubmitPrompt(text="Hello")))
    old_id = controller.snapshot().session_id
    tuple(controller.dispatch(ExecuteSlashCommand(raw="/new")))
    new_id = controller.snapshot().session_id
    assert new_id != old_id
    assert controller.conversation.snapshot() == ()
    store.inner.load(old_id, workspace)
    tuple(controller.dispatch(ExecuteSlashCommand(raw="/clear")))
    assert controller.clear_display_requested is True
    assert controller.snapshot().session_id != new_id


def test_exit_appends_closed_and_missing_closed_is_still_loadable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller, store = make_persistent_controller(
        workspace, [ModelTurn(assistant_text="你好", finish_reason="stop")]
    )
    tuple(controller.dispatch(SubmitPrompt(text="Hello")))
    open_id = controller.snapshot().session_id
    loaded = store.inner.load(open_id, workspace)
    assert all(record.type != "session.closed" for record in loaded.records)
    tuple(controller.dispatch(ExecuteSlashCommand(raw="/exit")))
    closed = store.inner.load(open_id, workspace)
    assert closed.records[-1].type == "session.closed"


def test_queue_flush_waits_until_current_turn_save_settles(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller, store = make_persistent_controller(
        workspace,
        [
            ModelTurn(assistant_text="first", finish_reason="stop"),
            ModelTurn(assistant_text="second", finish_reason="stop"),
        ],
    )
    controller.mark_active("run_1")
    tuple(controller.dispatch(QueuePrompt(text="follow up")))
    controller._active_run_id = None
    store.fail_on = "append_turn"
    outputs = tuple(controller.dispatch(SubmitPrompt(text="first")))
    types = [item.type for item in outputs if isinstance(item, EventEnvelope)]
    persist_at = types.index("session.persistence_changed")
    flushed_at = types.index("session.prompt_queue_flushed")
    assert persist_at < flushed_at
    assert types.count("run.completed") == 2
