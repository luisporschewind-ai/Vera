from vera.terminal.animation import AnimationClock


def test_disabled_animation_is_static() -> None:
    clock = {"t": 0.0}

    def tick() -> float:
        clock["t"] += 1.0
        return clock["t"]

    anim = AnimationClock(enabled=False, clock=tick)
    assert anim.frame() == anim.frame()


def test_enabled_animation_changes_over_time() -> None:
    clock = {"t": 0.0}

    def tick() -> float:
        return clock["t"]

    anim = AnimationClock(enabled=True, fps=10, clock=tick)
    first = anim.frame()
    clock["t"] = 0.2
    second = anim.frame()
    assert first != second


def test_wave_phase_advances_slowly() -> None:
    clock = {"t": 0.0}
    anim = AnimationClock(enabled=True, clock=lambda: clock["t"])
    start = anim.wave_phase()
    clock["t"] = 1.0
    delta = (anim.wave_phase() - start) % 1.0
    assert 0.15 < delta < 0.35
