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


def test_activity_phases_have_distinct_fixed_width_motion() -> None:
    anim = AnimationClock(enabled=True, fps=10, clock=lambda: 0.0)
    frames = [anim.frame(phase) for phase in ("thinking", "replying", "tool", "verify")]
    assert len(set(frames[:3])) == 3
    assert all(len(frame) == 3 for frame in frames)


def test_disabled_motion_stays_static_across_ticks_and_phases() -> None:
    now = [0.0]
    anim = AnimationClock(enabled=False, clock=lambda: now[0])
    first = anim.frame("replying")
    now[0] = 3.0
    assert anim.frame("replying") == first
    assert len(first) == 3


def test_wave_phase_advances_slowly() -> None:
    clock = {"t": 0.0}
    anim = AnimationClock(enabled=True, clock=lambda: clock["t"])
    start = anim.wave_phase()
    clock["t"] = 1.0
    delta = (anim.wave_phase() - start) % 1.0
    assert 0.35 < delta < 0.45
