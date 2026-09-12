from vera.terminal.animation import AnimationClock
from vera.terminal.capabilities import detect_display_capabilities
from vera.terminal.streaming import MAX_ANIMATION_FPS, MAX_STREAM_FPS, stream_interval_seconds


def test_capabilities_are_conservative_without_color_or_tty() -> None:
    no_color = detect_display_capabilities(
        {"NO_COLOR": "1", "TERM": "xterm-256color"},
        stdout_tty=True,
        animations_config=True,
    )
    assert no_color.color is False
    assert no_color.animations is False
    dumb = detect_display_capabilities(
        {"TERM": "dumb"},
        stdout_tty=True,
        animations_config=True,
    )
    assert dumb.color is False
    assert dumb.animations is False
    static = detect_display_capabilities(
        {"VERA_NO_ANIMATIONS": "1", "TERM": "xterm-256color"},
        stdout_tty=True,
        animations_config=True,
    )
    assert static.animations is False
    assert static.reduced_motion is True
    notty = detect_display_capabilities(
        {"TERM": "xterm-256color"},
        stdout_tty=False,
        animations_config=True,
    )
    assert notty.tty is False
    assert notty.animations is False
    clock = AnimationClock(enabled=True, fps=99)
    assert clock.fps <= MAX_ANIMATION_FPS
    assert stream_interval_seconds(99) == 1 / MAX_STREAM_FPS
