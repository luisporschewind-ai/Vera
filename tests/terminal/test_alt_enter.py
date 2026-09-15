from textual._xterm_parser import XTermParser

from vera.terminal.alt_enter import install_alt_enter_mapping


def test_terminal_alt_enter_sequence_is_not_plain_enter() -> None:
    install_alt_enter_mapping()
    parser = XTermParser()
    keys = [event.key for event in parser._sequence_to_key_events("\x1b\r")]
    assert keys == ["alt+enter"]
    keys = [event.key for event in parser._sequence_to_key_events("\r", alt=True)]
    assert keys == ["alt+enter"]
    keys = [event.key for event in parser._sequence_to_key_events("\r")]
    assert keys == ["enter"]
    keys = [event.key for event in parser.feed("\x1b\r")]
    assert keys == ["alt+enter"]
