from vera.presentation.disclosure import DisclosurePolicy
from vera.presentation.sanitize import sanitize_terminal_text
from vera.presentation.timeline import BlockKind, BlockStatus


def test_untrusted_osc_and_ansi_are_removed() -> None:
    value = "safe\x1b]52;c;secret\x07\x1b[31mred\x1b[0m"
    assert sanitize_terminal_text(value) == "safered"


def test_keeps_newlines_and_tabs() -> None:
    assert sanitize_terminal_text("a\tb\nc") == "a\tb\nc"
