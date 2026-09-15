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
        ("recovery.detected", "已列出待恢复任务"),
        ("recovery.resume_started", "正在恢复"),
        ("run.failed", "失败"),
    ],
)
def test_activity_labels_are_derived_from_events(event_type: str, label: str) -> None:
    payload = {"name": "read_file"} if event_type == "tool.started" else {}
    state = ActivityPresenter().apply(event(event_type, payload))
    assert state.label == label


def test_recovery_inspection_is_not_an_active_run() -> None:
    state = ActivityPresenter().apply(event("recovery.detected"))
    assert state.active is False
    assert state.label == "已列出待恢复任务"


def test_resume_started_keeps_recovery_active() -> None:
    state = ActivityPresenter().apply(event("recovery.resume_started"))
    assert state.active is True
    assert state.label == "正在恢复"
