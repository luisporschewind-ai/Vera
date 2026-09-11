from datetime import UTC, datetime

import pytest

from vera.contracts.events import EventEnvelope
from vera.presentation.activity import ActivityPresenter


def event(event_type: str, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id="e1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


@pytest.mark.parametrize(
    ("event_type", "label"),
    [
        ("model.requested", "正在思考"),
        ("tool.started", "正在读取"),
        ("approval.required", "等待审批"),
        ("changeset.applied", "正在验证"),
        ("recovery.detected", "正在恢复"),
        ("run.failed", "失败"),
    ],
)
def test_activity_labels_are_derived_from_events(event_type: str, label: str) -> None:
    payload = {"name": "read_file"} if event_type == "tool.started" else {}
    assert ActivityPresenter().apply(event(event_type, payload)).label == label
