"""Textual terminal presentation for Vera. Core types stay UI-independent."""

from vera.terminal.mode import PresentationMode, TerminalCapabilities, TerminalModeError, select_mode

__all__ = [
    "PresentationMode",
    "TerminalCapabilities",
    "TerminalModeError",
    "select_mode",
]
