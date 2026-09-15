from pathlib import Path

import pytest

from vera.contracts.sessions import ConversationTurn
from vera.persistence.session_store import ConversationSessionStore
from vera.redaction import Redactor
from vera.session.startup import SessionOpenRequest, SessionStartupError, SessionStartupService


def make_service(tmp_path: Path) -> tuple[SessionStartupService, ConversationSessionStore, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ConversationSessionStore(tmp_path / "state", "install-test", Redactor([]))
    return SessionStartupService(store), store, workspace


def test_new_always_creates_even_when_history_exists(tmp_path: Path) -> None:
    service, store, workspace = make_service(tmp_path)
    first = service.resolve(SessionOpenRequest(mode="new"), workspace, interactive_tty=True)
    store.append_turn(
        first.session_id,
        ConversationTurn(
            user_text="Hello",
            assistant_text="你好",
            run_id="run_1",
            terminal_state="response",
        ),
    )
    second = service.resolve(SessionOpenRequest(mode="new"), workspace, interactive_tty=True)
    assert second.session_id != first.session_id
    assert second.model_messages == ()


def test_continue_picks_latest_recoverable_or_fails(tmp_path: Path) -> None:
    service, store, workspace = make_service(tmp_path)
    with pytest.raises(SessionStartupError) as missing:
        service.resolve(SessionOpenRequest(mode="continue"), workspace, interactive_tty=True)
    assert missing.value.code == "no_matching_session"
    older = store.create(workspace)
    store.append_turn(
        older.session_id,
        ConversationTurn(
            user_text="old",
            assistant_text="older",
            run_id="run_old",
            terminal_state="response",
        ),
    )
    newer = store.create(workspace)
    store.append_turn(
        newer.session_id,
        ConversationTurn(
            user_text="new",
            assistant_text="newer",
            run_id="run_new",
            terminal_state="response",
        ),
    )
    loaded = service.resolve(SessionOpenRequest(mode="continue"), workspace, interactive_tty=True)
    assert loaded.session_id == newer.session_id


def test_resume_id_rejects_missing_and_workspace_mismatch(tmp_path: Path) -> None:
    service, store, workspace = make_service(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    created = store.create(workspace)
    with pytest.raises(SessionStartupError) as missing:
        service.resolve(
            SessionOpenRequest(mode="resume_id", session_id="missing"),
            workspace,
            interactive_tty=True,
        )
    assert missing.value.code in {"session_not_found", "invalid_session_record"}
    with pytest.raises(SessionStartupError) as mismatch:
        service.resolve(
            SessionOpenRequest(mode="resume_id", session_id=created.session_id),
            other,
            interactive_tty=True,
        )
    assert mismatch.value.code == "session_workspace_mismatch"


def test_picker_without_tty_requires_explicit_id(tmp_path: Path) -> None:
    service, _store, workspace = make_service(tmp_path)
    with pytest.raises(SessionStartupError) as exc:
        service.resolve(SessionOpenRequest(mode="resume_picker"), workspace, interactive_tty=False)
    assert exc.value.code == "picker_requires_id"
