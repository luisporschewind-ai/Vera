from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.session.queries import collect_diffs, resolve_run_id, usage_snapshot


def _event(event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload,
    )


def test_collect_diffs_and_missing_usage_are_unavailable() -> None:
    events = (
        _event(
            "changeset.proposed",
            {"files": [{"path": "a.py", "unified_diff": "--- a\n+++ b\n"}]},
        ),
    )
    files = collect_diffs(events)
    assert files[0]["path"] == "a.py"
    usage = usage_snapshot(())
    assert usage["calls"] == "unavailable"
    assert usage["total_tokens"] == "unavailable"
    assert 0 not in usage.values()
    assert usage["cache_hit_input_tokens"] == "unavailable"


def test_usage_snapshot_aggregates_complete_cache_detail() -> None:
    events = (
        _event(
            "model.completed",
            {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": 110,
                    "cache_hit_input_tokens": 40,
                    "cache_miss_input_tokens": 60,
                }
            },
        ),
        _event(
            "model.completed",
            {
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 5,
                    "total_tokens": 55,
                    "cache_hit_input_tokens": 30,
                    "cache_miss_input_tokens": 20,
                }
            },
        ),
    )
    usage = usage_snapshot(events)
    assert usage["calls"] == 2
    assert usage["input_tokens"] == 150
    assert usage["cache_hit_input_tokens"] == 70
    assert usage["cache_miss_input_tokens"] == 80
    assert usage["cache_hit_percent"] == 46.7


def test_old_journal_call_does_not_erase_known_total_usage() -> None:
    events = (
        _event(
            "model.completed",
            {"usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}},
        ),
        _event(
            "model.completed",
            {
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 5,
                    "total_tokens": 55,
                    "cache_hit_input_tokens": 30,
                    "cache_miss_input_tokens": 20,
                }
            },
        ),
    )
    usage = usage_snapshot(events)
    assert usage["input_tokens"] == 150
    assert usage["cache_hit_input_tokens"] == "unavailable"
    assert usage["cache_hit_percent"] == "unavailable"


def test_invalid_or_zero_cache_detail_never_creates_misleading_percent() -> None:
    invalid = usage_snapshot(
        (
            _event(
                "model.completed",
                {
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 1,
                        "total_tokens": 11,
                        "cache_hit_input_tokens": True,
                        "cache_miss_input_tokens": 9,
                    }
                },
            ),
        )
    )
    assert invalid["input_tokens"] == 10
    assert invalid["cache_hit_input_tokens"] == "unavailable"
    zero = usage_snapshot(
        (
            _event(
                "model.completed",
                {
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "cache_hit_input_tokens": 0,
                        "cache_miss_input_tokens": 0,
                    }
                },
            ),
        )
    )
    assert zero["cache_hit_input_tokens"] == 0
    assert zero["cache_hit_percent"] == "unavailable"


def test_resolve_run_id_falls_back_to_latest_store_run() -> None:
    class _Store:
        def __init__(self, run_id: str | None) -> None:
            self._run_id = run_id

        def list_runs(self) -> tuple[object, ...]:
            if self._run_id is None:
                return ()
            return (type("Run", (), {"run_id": self._run_id})(),)

    store = _Store("run_last")
    assert resolve_run_id(store, "requested", "active") == "requested"  # type: ignore[arg-type]
    assert resolve_run_id(store, None, "active") == "active"  # type: ignore[arg-type]
    assert resolve_run_id(store, None, None) == "run_last"  # type: ignore[arg-type]
    assert resolve_run_id(_Store(None), None, None) is None  # type: ignore[arg-type]
