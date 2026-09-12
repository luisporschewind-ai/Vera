from pathlib import Path

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


def test_completion_list_shows_path_mentions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("x", encoding="utf-8")
    widget = CompletionList()
    items = widget.update_for_path("not", workspace)
    assert items[0].relative_path == "notes.md"
    assert widget.display is True
    widget.update_for_prefix(
        "hello",
        SessionSnapshot(
            session_id="s1",
            active_run_id=None,
            pending_approval_id=None,
            model_profile="fake",
            closed=False,
        ),
    )
    assert widget.display is False
