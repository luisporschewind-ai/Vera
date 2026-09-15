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
