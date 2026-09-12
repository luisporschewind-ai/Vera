from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.errors import explain_failure


def test_failure_copy_covers_what_side_effects_and_next() -> None:
    event = EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="run.failed",
        payload={"reason": "provider_timeout"},
    )
    explained = explain_failure(event)
    assert "失败" in explained["what"]
    assert explained["side_effects"]
    assert explained["next"]
    expired = explain_failure(event.model_copy(update={"type": "approval.expired", "payload": {}}))
    assert "过期" in expired["what"]
    assert "重新生成" in expired["next"]
