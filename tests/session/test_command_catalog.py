from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionSnapshot


def _snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )


def test_slash_completion_comes_from_shared_catalog() -> None:
    catalog = CommandCatalog()
    names = [item.name for item in catalog.list("/rec", _snapshot())]
    assert names == ["/recover"]
    assert [item.name for item in catalog.list("/DOC", _snapshot())] == ["/doctor"]


def test_context_full_still_lists_compact_and_new() -> None:
    catalog = CommandCatalog()
    names = {item.name for item in catalog.list("/", _snapshot())}
    assert "/compact" in names
    assert "/new" in names
    assert "/doctor" in names
    assert "/diff" in names


def test_help_is_grouped_and_unknown_command_suggests() -> None:
    catalog = CommandCatalog()
    help_text = catalog.help_text(_snapshot())
    assert "开始" in help_text
    assert "安全" in help_text
    assert "/doctor" in help_text
    parsed = catalog.parse(["/docotr"])
    assert parsed.unknown is True
    assert "/doctor" in parsed.suggestions
    known = catalog.parse(["/theme", "no-color"])
    assert known.unknown is False
    assert known.handler == "theme"
    assert known.args == ("no-color",)
