from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.session.queries import collect_diffs, usage_snapshot


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
