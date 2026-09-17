from vera.terminal.brand import select_brand_mark
from vera.terminal.display import display_width


def test_full_mark_at_80x24_unicode() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    assert mark.mode == "full"
    assert len(mark.lines) == 3
    assert mark.accessible_label == "Vera"
    assert display_width(mark.lines[0]) <= 80


def test_compact_after_first_task() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False, expanded=False)
    assert mark.mode == "compact"
    assert mark.lines == ("VERA",)


def test_ascii_when_unicode_unavailable() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=False, no_color=False)
    assert mark.mode == "ascii"
    assert len(mark.lines) == 3
    joined = "\n".join(mark.lines)
    assert joined.isascii()
    assert "\x1b" not in joined
    shrunk = select_brand_mark(columns=80, rows=24, unicode=False, no_color=False, expanded=False)
    assert shrunk.lines[0] == "VERA"


def test_no_nerd_font_or_emoji() -> None:
    for unicode_on in (True, False):
        mark = select_brand_mark(columns=80, rows=24, unicode=unicode_on, no_color=True)
        text = "".join(mark.lines)
        assert all(ord(char) < 0xE000 or ord(char) > 0xF8FF for char in text)
        assert "★" not in text
        assert "[V]" not in text


def test_clips_to_available_columns() -> None:
    mark = select_brand_mark(columns=3, rows=24, unicode=True, no_color=False)
    assert display_width(mark.lines[0]) <= 3
    assert mark.accessible_label == "Vera"


def test_cjk_neighbor_does_not_widen_mark() -> None:
    mark = select_brand_mark(columns=8, rows=16, unicode=True, no_color=False, expanded=False)
    neighbor = mark.lines[0] + "深海"
    assert display_width(mark.lines[0]) <= 8
    assert neighbor.startswith("VERA")
