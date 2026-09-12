from vera.terminal.theme import normalize_theme, theme_class


def test_theme_is_session_only_and_named() -> None:
    assert normalize_theme(None) == "default"
    assert normalize_theme("high-contrast") == "high-contrast"
    assert normalize_theme("no-color") == "no-color"
    assert normalize_theme("executable.py") is None
    assert theme_class("default") == "theme-default"
