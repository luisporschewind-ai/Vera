from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionSnapshot
from vera.terminal.widgets.completions import CompletionList


def test_completion_list_filters_prefix() -> None:
    widget = CompletionList()
    snapshot = SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )
    items = widget.update_for_prefix("/hel", snapshot)
    assert [item.name for item in items] == ["/help"]
    assert widget.display is True
    empty = widget.update_for_prefix("hello", snapshot)
    assert empty == ()
    assert widget.display is False
    assert isinstance(widget.catalog, CommandCatalog)
