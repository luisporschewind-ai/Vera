from vera.terminal.widgets.diff_view import DiffFile, DiffView


def test_diff_view_navigates_copies_and_truncates() -> None:
    view = DiffView(
        (
            DiffFile(path="a.py", unified_diff="--- a\n+++ b\n+added\n"),
            DiffFile(path="b.py", unified_diff="--- a\n+++ b\n-removed\n"),
        )
    )
    assert view.current is not None
    assert view.current.path == "a.py"
    assert "+" in view.visible_text()
    assert view.copy_text() == "--- a\n+++ b\n+added\n"
    assert "\x1b" not in view.copy_text()
    assert view.next_file() is not None
    assert view.current.path == "b.py"
    empty = DiffView(())
    assert empty.visible_text() == "没有 Diff。"
    huge = DiffView((DiffFile(path="big.py", unified_diff="+" * 30_000),), max_chars=100)
    assert huge.truncated() is True
    assert "[truncated]" in huge.visible_text()
