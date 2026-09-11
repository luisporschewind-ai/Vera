from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionSnapshot


def test_slash_completion_comes_from_shared_catalog() -> None:
    catalog = CommandCatalog()
    snapshot = SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )
    names = [item.name for item in catalog.list("/rec", snapshot)]
    assert names == ["/recover"]


def test_context_full_still_lists_compact_and_new() -> None:
    catalog = CommandCatalog()
    snapshot = SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )
    names = {item.name for item in catalog.list("/", snapshot)}
    assert "/compact" in names
    assert "/new" in names
