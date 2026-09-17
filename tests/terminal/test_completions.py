from pathlib import Path

from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionSnapshot
from vera.terminal.widgets.completions import (
    CompletionAccept,
    CompletionList,
    replace_path_mention,
    resolve_slash_query,
)


def _snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )


def test_completion_list_filters_prefix() -> None:
    widget = CompletionList()
    snapshot = _snapshot()
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
    widget.update_for_prefix("hello", _snapshot())
    assert widget.display is False


def test_path_completion_accepts_mention_without_submit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "ViewController.swift").write_text("x", encoding="utf-8")
    widget = CompletionList()
    items = widget.update_for_path("", workspace)
    assert items[0].display == "ViewController.swift"
    assert widget.accept("@") == CompletionAccept(
        text="@ViewController.swift ",
        submit=False,
    )
    assert widget.accept("看看 @View") == CompletionAccept(
        text="看看 @ViewController.swift ",
        submit=False,
    )


def test_replace_path_mention_keeps_leading_text() -> None:
    assert replace_path_mention("@", "notes.md") == "@notes.md "
    assert replace_path_mention("看 @App/", "App/ViewController.swift") == (
        "看 @App/ViewController.swift "
    )
    assert replace_path_mention("no mention", "notes.md") == "@notes.md "


def test_slash_completion_highlights_and_accepts_prefix() -> None:
    widget = CompletionList()
    items = widget.update_for_prefix("/th", _snapshot())
    assert [item.name for item in items] == ["/theme"]
    assert widget.accept("/th") == CompletionAccept(text="/theme ", submit=False)
    widget.update_for_input("/theme ", _snapshot())
    assert widget.accept("/theme ") == CompletionAccept(text="/theme default", submit=True)
    widget.update_for_prefix("/th", _snapshot())
    assert widget.accepted_slash_command("/theme high-contrast") == "/theme high-contrast"
    assert "▸" in widget.visible_text()
    assert "/theme" in widget.visible_text()
    assert widget.has_selection_style is True
    assert "on #" in str(widget.content)


def test_slash_completion_arrows_change_selection() -> None:
    widget = CompletionList()
    widget.update_for_prefix("/", _snapshot())
    assert widget.accepted_slash_command("/") == "/help"
    assert widget.navigate(1) is True
    assert widget.accepted_slash_command("/") == "/status"
    assert widget.navigate(-1) is True
    assert widget.accepted_slash_command("/") == "/help"


def test_slash_completion_keeps_all_matches_and_stays_visible() -> None:
    widget = CompletionList()
    items = widget.update_for_prefix("/", _snapshot())
    names = [item.name for item in items]
    assert "/help" in names
    assert "/doctor" in names
    assert "/theme" in names
    assert "/exit" in names
    assert len(names) == len(widget.catalog.all())
    assert "斜杠命令 · " in widget.visible_text()
    assert "/help" in widget.visible_text()
    while widget.accepted_slash_command("/") != "/doctor":
        assert widget.navigate(1) is True
    assert "/doctor" in widget.visible_text()
    assert "检查本地环境与配置" in widget.visible_text()
    filtered = widget.update_for_prefix("/do", _snapshot())
    assert [item.name for item in filtered] == ["/doctor"]
    assert widget.display is True
    assert "斜杠命令 · 1" in widget.visible_text()
    assert "/doctor" in widget.visible_text()
    assert widget.has_selection_style is True
    assert "on #" in str(widget.content)
    missing = widget.update_for_prefix("/zzz", _snapshot())
    assert missing == ()
    assert widget.display is True
    assert "没有匹配的命令" in widget.visible_text()


def test_slash_completion_is_case_insensitive() -> None:
    widget = CompletionList()
    items = widget.update_for_prefix("/DOC", _snapshot())
    assert [item.name for item in items] == ["/doctor"]


def test_resolve_slash_query_recovers_ime_and_misplaced_letters() -> None:
    snapshot = _snapshot()
    catalog = CommandCatalog()
    assert resolve_slash_query("/do", active=True, catalog=catalog, snapshot=snapshot) == "/do"
    assert resolve_slash_query("do", active=True, catalog=catalog, snapshot=snapshot) == "/do"
    assert resolve_slash_query("d/", active=True, catalog=catalog, snapshot=snapshot) == "/d"
    assert resolve_slash_query("hello", active=True, catalog=catalog, snapshot=snapshot) is None
    assert resolve_slash_query("", active=True, catalog=catalog, snapshot=snapshot) is None
    assert resolve_slash_query("do", active=False, catalog=catalog, snapshot=snapshot) is None
    assert (
        resolve_slash_query(
            "@App/ViewController.swift 分析此文件",
            active=False,
            catalog=catalog,
            snapshot=snapshot,
        )
        is None
    )
    assert (
        resolve_slash_query(
            "@App/ViewController.swift 分析此文件",
            active=True,
            catalog=catalog,
            snapshot=snapshot,
        )
        is None
    )


def test_path_mention_does_not_open_slash_completion() -> None:
    widget = CompletionList()
    snapshot = _snapshot()
    widget.update_for_prefix("/", snapshot)
    assert widget.update_for_input("@App/ViewController.swift 分析此文件", snapshot) is False
    assert widget.display is False


def test_slash_popup_stays_up_when_slash_is_eaten() -> None:
    widget = CompletionList()
    snapshot = _snapshot()
    widget.update_for_prefix("/", snapshot)
    assert widget.update_for_input("", snapshot) is True
    assert widget.display is True
    assert widget.update_for_input("do", snapshot) is True
    assert widget.needs_restore is True
    assert widget.last_query == "/do"
    assert [item.name for item in widget._slash_items] == ["/doctor"]
    assert widget.update_for_input("hello", snapshot) is False
