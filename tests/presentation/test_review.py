from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.review import project_review


def test_review_is_deterministic_and_does_not_invent_facts() -> None:
    events = (
        EventEnvelope(
            event_id="e1",
            run_id="run_1",
            sequence=1,
            timestamp=datetime(2026, 9, 13, tzinfo=UTC),
            type="changeset.proposed",
            payload={"files": [{"path": "a.py"}], "risk": "medium"},
        ),
        EventEnvelope(
            event_id="e2",
            run_id="run_1",
            sequence=2,
            timestamp=datetime(2026, 9, 13, tzinfo=UTC),
            type="approval.required",
            payload={"kind": "changeset", "risk": "medium"},
        ),
        EventEnvelope(
            event_id="e3",
            run_id="run_1",
            sequence=3,
            timestamp=datetime(2026, 9, 13, tzinfo=UTC),
            type="verification.completed",
            payload={"status": "passed", "exit_code": 0},
        ),
    )
    first = project_review(events)
    second = project_review(events)
    assert first == second
    assert first["files"] == ["a.py"]
    assert first["side_effects"] is False
    assert first["verifications"][0]["status"] == "passed"
