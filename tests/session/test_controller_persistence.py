from pathlib import Path

from tests.session.controller_helpers import (
    make_persistent_controller,
)
from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import ConversationTurn
from vera.models.base import ModelTurn
from vera.session.actions import (
    CloseSession,
    ExecuteSlashCommand,
    QueuePrompt,
    SubmitPrompt,
)


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
    assert second.conversation_stats().source == "resumed"
    assert second.conversation_stats().persistent_state == "saved"
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
    events = [
        item
        for item in controller.dispatch(ExecuteSlashCommand(raw="/new"))
        if isinstance(item, EventEnvelope)
    ]
    new_id = controller.snapshot().session_id
    assert new_id != old_id
    assert controller.conversation.snapshot() == ()
    assert controller.clear_display_requested is True
    assert controller.session_source == "new"
    assert events[0].payload.get("clear_display") is True
    assert all(item.type != "session.status" for item in events)
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
