"""Import contracts for SessionController's extracted flow modules."""

from vera.session.command_flow import SessionCommandFlow
from vera.session.editor_flow import SessionEditorFlow
from vera.session.persistence_flow import SessionPersistenceFlow
from vera.session.run_flow import SessionRunFlow


def test_session_flow_facades_are_available() -> None:
    assert SessionCommandFlow is not None
    assert SessionEditorFlow is not None
    assert SessionPersistenceFlow is not None
    assert SessionRunFlow is not None
    assert callable(SessionRunFlow.dispatch)
    assert callable(SessionPersistenceFlow.persist_turn)
    assert callable(SessionEditorFlow.open_editor)
    assert callable(SessionCommandFlow.slash)
