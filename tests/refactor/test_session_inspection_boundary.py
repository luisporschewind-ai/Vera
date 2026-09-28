"""Import contract for SessionController command handlers."""

from vera.session.inspection_flow import SessionInspectionFlow


def test_session_inspection_flow_facade_is_available() -> None:
    assert SessionInspectionFlow is not None
    assert callable(SessionInspectionFlow.permissions)
    assert callable(SessionInspectionFlow.diff)
    assert callable(SessionInspectionFlow.theme)
