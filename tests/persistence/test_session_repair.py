from datetime import UTC, datetime
from pathlib import Path

import pytest

from vera.contracts.sessions import ConversationTurn
from vera.persistence.errors import JournalCorrupt
from vera.persistence.session_store import ConversationSessionStore
from vera.redaction import Redactor


def _store(tmp_path: Path) -> tuple[ConversationSessionStore, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    ids = iter(("session_src", "session_copy", "session_extra"))
    times = iter(datetime(2026, 9, 16, 7, index, tzinfo=UTC) for index in range(1, 12))
    store = ConversationSessionStore(
        tmp_path / "state",
        "install-test",
        Redactor([]),
        id_factory=lambda: next(ids),
        clock=lambda: next(times),
    )
    return store, workspace


def test_tail_truncation_can_copy_without_changing_source(tmp_path: Path) -> None:
    store, workspace = _store(tmp_path)
    created = store.create(workspace)
    store.append_turn(
        created.session_id,
        ConversationTurn(
            user_text="你好",
            assistant_text="你好。",
            run_id=None,
            terminal_state="response",
        ),
    )
    journal = tmp_path / "state" / "sessions" / created.session_id / "session.jsonl"
    before = journal.read_bytes()
    journal.write_bytes(before + b'{"session_format_version":1')
    plan = store.inspect_repair(created.session_id, workspace)
    assert plan.repairable_tail_only is True
    copied = store.create_repaired_copy(plan, workspace)
    assert copied.session_id == "session_copy"
    assert copied.records[0].payload.repaired_from_session_id == "session_src"
    assert journal.read_bytes() == before + b'{"session_format_version":1'
    assert copied.history_messages[0].content == "你好"


def test_mid_file_damage_is_not_repairable_and_plan_expires(tmp_path: Path) -> None:
    store, workspace = _store(tmp_path)
    created = store.create(workspace)
    journal = tmp_path / "state" / "sessions" / created.session_id / "session.jsonl"
    journal.write_text("not-json\n" + journal.read_text(encoding="utf-8"), encoding="utf-8")
    plan = store.inspect_repair(created.session_id, workspace)
    assert plan.repairable_tail_only is False
    with pytest.raises(JournalCorrupt):
        store.create_repaired_copy(plan, workspace)

    store_ok, workspace_ok = _store(tmp_path / "ok")
    fresh = store_ok.create(workspace_ok)
    path = tmp_path / "ok" / "state" / "sessions" / fresh.session_id / "session.jsonl"
    path.write_bytes(path.read_bytes() + b"{")
    good_plan = store_ok.inspect_repair(fresh.session_id, workspace_ok)
    path.write_bytes(path.read_bytes() + b"extra")
    with pytest.raises(JournalCorrupt) as expired:
        store_ok.create_repaired_copy(good_plan, workspace_ok)
    assert "expired" in str(expired.value).lower() or expired.value.code == "invalid_session_record"
