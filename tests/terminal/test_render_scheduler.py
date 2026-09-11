from vera.terminal.render_scheduler import RenderScheduler


def test_scheduler_batches_within_interval() -> None:
    clock = {"now": 0.0}

    def tick() -> float:
        return clock["now"]

    scheduler = RenderScheduler(interval_seconds=0.05, clock=tick)
    assert scheduler.submit("a", 1) is True
    scheduler.flush()
    clock["now"] = 0.01
    assert scheduler.submit("a", 2) is False
    assert scheduler.submit("a", 3) is False
    assert scheduler.pending_count == 1
    clock["now"] = 0.06
    assert scheduler.submit("b", 4) is True
    flushed = scheduler.flush()
    assert flushed == {"a": 3, "b": 4}
