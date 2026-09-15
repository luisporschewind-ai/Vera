from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.sessions import ConversationTurn
from vera.persistence.session_store import ConversationSessionStore
from vera.redaction import Redactor


def _store(
    tmp_path: Path, *, stamp: datetime | None = None
) -> tuple[ConversationSessionStore, Path]:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ids = iter(("session_a", "session_b", "session_c"))
    times = iter(
        (
            datetime(2026, 9, 16, 6, 0, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 1, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 2, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 3, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 4, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 5, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 6, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 7, tzinfo=UTC),
            datetime(2026, 9, 16, 6, 8, tzinfo=UTC),
        )
    )
    store = ConversationSessionStore(
        state,
        "install-test",
        Redactor([]),
        id_factory=lambda: next(ids),
        clock=lambda: stamp or next(times),
    )
    return store, workspace


def test_create_append_title_and_latest(tmp_path: Path) -> None:
    store, workspace = _store(tmp_path)
    created = store.create(workspace)
    assert created.title == "新会话"
    turn = store.append_turn(
        created.session_id,
        ConversationTurn(
            user_text="列出文件\n第二行",
            assistant_text="有 README.md。",
            run_id="run_missing",
            terminal_state="completed",
        ),
    )
    loaded = store.load(created.session_id, workspace)
    assert turn.type == "turn.committed"
    assert loaded.title == "列出文件"
    assert loaded.history_messages[0].content.startswith("列出文件")
    assert loaded.model_messages[0].role == "user"
    listed = store.list_for_workspace(workspace)
    assert listed[0].latest_run_id == "run_missing"
    assert listed[0].latest_run_state == "unavailable"
    other = tmp_path / "other"
    other.mkdir()
    store.create(other)
    assert [item.session_id for item in store.list_for_workspace(workspace)] == ["session_a"]
    latest = store.latest_for_workspace(workspace)
    assert latest is not None
    assert latest.session_id == "session_a"


def test_compaction_projects_summary_then_new_turns(tmp_path: Path) -> None:
    store, workspace = _store(tmp_path)
    created = store.create(workspace)
    store.append_turn(
        created.session_id,
        ConversationTurn(
            user_text="先问",
            assistant_text="先答",
            run_id=None,
            terminal_state="response",
        ),
    )
    loaded = store.load(created.session_id, workspace)
    through = loaded.records[-1].sequence
    store.append_compaction(created.session_id, "摘要：先问先答", through)
    store.append_turn(
        created.session_id,
        ConversationTurn(
            user_text="再问",
            assistant_text="再答",
            run_id=None,
            terminal_state="response",
        ),
    )
    restored = store.load(created.session_id, workspace)
    assert restored.compaction_count == 1
    assert restored.model_messages[0].role == "summary"
    assert [message.content for message in restored.model_messages[1:]] == ["再问", "再答"]
    assert [message.content for message in restored.history_messages] == [
        "先问",
        "先答",
        "再问",
        "再答",
    ]
