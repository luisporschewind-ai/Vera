from datetime import UTC, datetime

import pytest

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame, StreamFrameType
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
        ("changeset.applied", "处理中"),
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


def test_run_started_resets_steps() -> None:
    presenter = ActivityPresenter()
    presenter.apply(event("tool.started", {"name": "read_file", "path": "a.py"}))
    presenter.apply(event("run.failed"))
    processing = presenter.apply(event("run.started", {}))
    assert processing.label == "处理中"
    assert processing.active is True
    assert processing.severity == "info"
    assert processing.steps == ()
    assert processing.target == ""
    state = presenter.apply(event("model.requested"))
    assert state.steps == ()
    assert state.target == ""
    assert state.label == "正在思考"


def test_run_started_and_finished_actions_do_not_claim_work_is_still_running() -> None:
    presenter = ActivityPresenter()
    assert presenter.apply(event("run.started")).phase == "processing"
    presenter.apply(event("tool.started", {"name": "read_file", "target": "a.py"}))
    assert presenter.apply(event("tool.completed")).phase == "processing"
    presenter.apply(event("tool.started", {"name": "propose_changeset"}))
    assert presenter.apply(event("changeset.proposed")).phase == "processing"
    assert presenter.apply(event("changeset.applied")).phase == "processing"
    presenter.apply(event("verification.started"))
    assert presenter.apply(event("verification.completed")).phase == "processing"


def test_first_text_delta_switches_thinking_to_replying_without_exposing_reasoning() -> None:
    presenter = ActivityPresenter()
    presenter.apply(event("run.started"))
    assert presenter.apply(event("model.requested")).phase == "thinking"
    frame = StreamFrame(
        run_id="run_1",
        stream_id="stream_1",
        index=0,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": "你好"},
    )
    state = presenter.apply(frame)
    assert state.phase == "replying"
    assert state.label == "正在回复"


def test_late_delta_cannot_reopen_terminal_run_or_override_next_run() -> None:
    presenter = ActivityPresenter()
    presenter.apply(event("run.started"))
    presenter.apply(event("run.completed"))
    old_frame = StreamFrame(
        run_id="run_1",
        stream_id="stream_1",
        index=0,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": "late"},
    )
    assert presenter.apply(old_frame).phase == "done"
    next_run = event("run.started").model_copy(update={"run_id": "run_2"})
    presenter.apply(next_run)
    assert presenter.apply(old_frame).phase == "processing"


def test_approval_is_static_waiting_state() -> None:
    state = ActivityPresenter().apply(event("approval.required"))
    assert state.phase == "approval"
    assert state.active is False


def test_late_text_from_previous_model_request_cannot_override_tool() -> None:
    presenter = ActivityPresenter()
    presenter.apply(event("run.started"))
    presenter.apply(event("model.requested"))
    presenter.apply(event("tool.started", {"name": "read_file"}))
    frame = StreamFrame(
        run_id="run_1",
        stream_id="stream_1",
        index=0,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": "late"},
    )
    assert presenter.apply(frame).phase == "tool"
