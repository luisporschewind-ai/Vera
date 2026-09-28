import json
from pathlib import Path

from rich.text import Text

from vera.terminal.brand import select_brand_mark
from vera.terminal.display import display_width
from vera.terminal.widgets.header import VeraHeader, logo_wave_value, wave_glyph_style


def test_full_mark_at_80x24_unicode() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    assert mark.mode == "full"
    assert len(mark.lines) == 4
    assert mark.accessible_label == "Vera"
    assert display_width(mark.lines[0]) <= 80


def test_compact_after_first_task() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False, expanded=False)
    assert mark.mode == "compact"
    assert mark.lines == ("VERA",)


def test_ascii_when_unicode_unavailable() -> None:
    mark = select_brand_mark(columns=80, rows=24, unicode=False, no_color=False)
    assert mark.mode == "ascii"
    assert len(mark.lines) == 4
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


def test_logo_wave_travels_bottom_left_to_top_right() -> None:
    bottom_left = logo_wave_value(row=3, column=0, phase=0.1)
    top_right = logo_wave_value(row=0, column=26, phase=0.1)
    assert bottom_left > top_right
    later = logo_wave_value(row=0, column=26, phase=0.85)
    assert later > 0.9
    assert later > logo_wave_value(row=3, column=0, phase=0.85)


def test_mark_matches_approved_v4_characters_and_every_dot() -> None:
    source = Path(__file__).resolve().parents[2] / "docs/evals/artifacts/vera-logo-v4.json"
    design = json.loads(source.read_text())
    mark = select_brand_mark(columns=80, rows=24, unicode=True, no_color=False)
    assert mark.lines == tuple(design["lines"])
    assert all(display_width(line) == 27 for line in mark.lines)
    expected = ["..".join(glyph[y] for glyph in design["glyphs"]) for y in range(16)]
    bits = ((0, 3), (1, 4), (2, 5), (6, 7))
    for row, line in enumerate(mark.lines):
        assert all(line[column] == " " for column in (6, 13, 20))
        for column, char in enumerate(line):
            mask = 0 if char == " " else ord(char) - 0x2800
            for dy, bit_row in enumerate(bits):
                for dx, bit in enumerate(bit_row):
                    assert bool(mask & (1 << bit)) == (
                        expected[row * 4 + dy][column * 2 + dx] == "#"
                    )
    ascii_mark = select_brand_mark(columns=80, rows=24, unicode=False, no_color=True)
    assert ascii_mark.lines == tuple(
        "".join("." if char != " " else " " for char in line) for line in mark.lines
    )


def test_static_and_animated_logo_keep_approved_strokes_without_extra_bold() -> None:
    header = VeraHeader()
    mark = header.current_mark()
    for phase in (None, 0.1, 0.5, 0.9):
        header.set_wave_phase(phase)
        visual = header._logo_visual(mark.lines)
        assert isinstance(visual, Text)
        assert visual.plain == "\n".join(mark.lines)
        assert visual.no_wrap
        assert visual.style.bold is False
        assert all(span.style.bold is False for span in visual.spans)


def test_logo_wave_crest_differs_from_trough_without_dim() -> None:
    crest = wave_glyph_style(0.8)
    trough = wave_glyph_style(0.1)
    assert crest != trough
    assert "dim" not in str(crest).lower()
    assert "dim" not in str(trough).lower()
