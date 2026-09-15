"""Map real-terminal Alt+Enter sequences onto a single Textual key.

macOS Terminal.app sends Option+Enter as ESC then CR. Textual's xterm parser
collects that as ``\\x1b\\r``, then reissues it as plain ``enter`` because the
``alt`` flag is ignored for CR. Without this mapping, Alt+Enter submits.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual import events
from textual._xterm_parser import XTermParser

_ALT_ENTER_SEQUENCES = frozenset({"\x1b\r", "\x1b\n"})
_ENTER_CHARACTERS = frozenset({"\r", "\n"})


def _is_alt_enter_sequence(sequence: str, alt: bool) -> bool:
    return sequence in _ALT_ENTER_SEQUENCES or (alt and sequence in _ENTER_CHARACTERS)


def _sequence_to_key_events(
    self: XTermParser, sequence: str, alt: bool = False
) -> Iterable[events.Key]:
    if _is_alt_enter_sequence(sequence, alt):
        yield events.Key("alt+enter", "\n")
        return
    yield from _ORIGINAL_SEQUENCE_TO_KEY_EVENTS(self, sequence, alt)


_ORIGINAL_SEQUENCE_TO_KEY_EVENTS = XTermParser._sequence_to_key_events
_sequence_to_key_events._vera_alt_enter = True  # type: ignore[attr-defined]


def install_alt_enter_mapping() -> None:
    current = XTermParser._sequence_to_key_events
    if getattr(current, "_vera_alt_enter", False):
        return
    XTermParser._sequence_to_key_events = _sequence_to_key_events  # type: ignore[method-assign]
