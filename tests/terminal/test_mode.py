import pytest

from vera.terminal.mode import (
    PresentationMode,
    TerminalCapabilities,
    TerminalModeError,
    select_mode,
)


def test_default_mode_is_tui_for_supported_terminal() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=True, stdout_tty=True, term="xterm-256color", columns=80, rows=24
    )
    assert select_mode(False, False, capabilities) is PresentationMode.TUI


def test_default_mode_requires_explicit_fallback_without_tty() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=False, stdout_tty=False, term="", columns=80, rows=24
    )
    with pytest.raises(TerminalModeError, match="--plain.*--json"):
        select_mode(False, False, capabilities)


def test_plain_and_json_are_mutual_exclusive() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=True, stdout_tty=True, term="xterm-256color", columns=80, rows=24
    )
    with pytest.raises(TerminalModeError, match="互斥"):
        select_mode(True, True, capabilities)


def test_dumb_terminal_rejects_default_tui() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=True, stdout_tty=True, term="dumb", columns=80, rows=24
    )
    with pytest.raises(TerminalModeError, match="--plain.*--json"):
        select_mode(False, False, capabilities)


@pytest.mark.parametrize(
    ("stdin_tty", "stdout_tty"),
    [(True, False), (False, True)],
)
def test_partial_tty_rejects_default_tui(stdin_tty: bool, stdout_tty: bool) -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=stdin_tty,
        stdout_tty=stdout_tty,
        term="xterm-256color",
        columns=80,
        rows=24,
    )
    with pytest.raises(TerminalModeError):
        select_mode(False, False, capabilities)


def test_explicit_plain_and_json_ignore_tty() -> None:
    capabilities = TerminalCapabilities(
        stdin_tty=False, stdout_tty=False, term="dumb", columns=40, rows=10
    )
    assert select_mode(True, False, capabilities) is PresentationMode.PLAIN
    assert select_mode(False, True, capabilities) is PresentationMode.JSON
