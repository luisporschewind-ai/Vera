"""Presentation mode selection without importing Textual."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PresentationMode(StrEnum):
    TUI = "tui"
    PLAIN = "plain"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class TerminalCapabilities:
    stdin_tty: bool
    stdout_tty: bool
    term: str
    columns: int
    rows: int

    @property
    def supports_tui(self) -> bool:
        if not self.stdin_tty or not self.stdout_tty:
            return False
        term = self.term.strip().lower()
        if not term or term == "dumb":
            return False
        return self.columns >= 1 and self.rows >= 1


class TerminalModeError(Exception):
    def __init__(self, reason_code: str, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message
        self.exit_code = exit_code


def select_mode(
    plain: bool,
    json_output: bool,
    capabilities: TerminalCapabilities,
) -> PresentationMode:
    if plain and json_output:
        raise TerminalModeError(
            "mode_conflict",
            "--plain 与 --json 互斥；请只指定其中一个。",
        )
    if plain:
        return PresentationMode.PLAIN
    if json_output:
        return PresentationMode.JSON
    if capabilities.supports_tui:
        return PresentationMode.TUI
    raise TerminalModeError(
        "tui_unsupported",
        "当前终端不支持默认 TUI；请使用 --plain 或 --json。",
    )
