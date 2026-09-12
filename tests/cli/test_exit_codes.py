from datetime import UTC, datetime

from vera.cli_exit_codes import (
    PROVIDER_OR_RUN_FAILED,
    SUCCESS,
    USER_CANCEL,
    VERIFICATION_FAILED,
    exit_code_for_events,
)
from vera.contracts.events import EventEnvelope


def _event(event_type: str, payload: dict[str, object] | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def test_exit_codes_do_not_confuse_cancel_failure_and_verification() -> None:
    assert exit_code_for_events([]) == 5
    assert exit_code_for_events([_event("run.completed")]) == SUCCESS
    assert (
        exit_code_for_events([_event("run.completed", {"state": "verification_failed"})])
        == VERIFICATION_FAILED
    )
    assert exit_code_for_events([_event("run.cancelled")]) == USER_CANCEL
    assert exit_code_for_events([_event("run.failed")]) == PROVIDER_OR_RUN_FAILED
