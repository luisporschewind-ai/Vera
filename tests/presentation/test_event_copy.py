from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.event_copy import (
    event_summary,
    event_title,
    format_recovery_inspection,
    format_tool_body,
    format_tool_title,
    is_silent,
)
from vera.presentation.projector import AppendBlock, TimelineProjector

# Every type the runtime or session controller can emit. A user-facing surface
# must never render these identifiers verbatim.
EMITTED_EVENT_TYPES = (
    "run.started",
    "run.completed",
    "run.failed",
    "run.cancelled",
    "model.requested",
    "model.completed",
    "model.failed",
    "model.retrying",
    "tool.started",
    "tool.completed",
    "changeset.proposed",
    "changeset.applied",
    "checkpoint.created",
    "checkpoint.restored",
    "checkpoint.restore_failed",
    "approval.required",
    "approval.resolved",
    "approval.expired",
    "approval.invalidated",
    "verification.started",
    "verification.completed",
    "conversation.compacted",
    "security.content_flagged",
    "security.findings_truncated",
    "recovery.detected",
    "recovery.abandoned",
    "recovery.manual_required",
    "recovery.restored",
    "recovery.restore_proposed",
    "recovery.resume_started",
    "recovery.resumed",
    "rollback.completed",
    "rollback.conflicted",
    "state.inspected",
    "state.migration_completed",
)


def event(event_type: str, *, sequence: int = 1, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def test_no_emitted_event_type_leaks_into_timeline_text() -> None:
    for index, event_type in enumerate(EMITTED_EVENT_TYPES, start=1):
        projector = TimelineProjector()
        mutations = projector.apply(
            event(event_type, sequence=index, payload={"status": "ok", "name": "read_file"})
        )
        for mutation in mutations:
            block = getattr(mutation, "block", None)
            if block is None:
                continue
            assert event_type not in block.title, f"{event_type} leaked into title"
            assert event_type not in block.body, f"{event_type} leaked into body"


def test_model_round_trips_do_not_create_blocks() -> None:
    projector = TimelineProjector()
    assert projector.apply(event("model.requested", payload={"turn": 1, "attempt": 1})) == ()
    assert projector.apply(event("model.completed", sequence=2, payload={"finish": "stop"})) == ()
    assert projector.apply(event("model.retrying", sequence=3, payload={"attempt": 2})) == ()
    assert projector.blocks() == ()


def test_payload_is_rendered_as_labelled_lines_not_dict_repr() -> None:
    projector = TimelineProjector()
    mutations = projector.apply(
        event("checkpoint.created", payload={"checkpoint_id": "cp_1", "status": "ready"})
    )
    block = mutations[0].block  # type: ignore[union-attr]
    assert block.title == "已创建检查点"
    assert "{" not in block.body
    assert "'" not in block.body
    assert "检查点：cp_1" in block.body
    assert "状态：ready" in block.body


def test_hidden_fields_and_value_rendering() -> None:
    summary = event_summary(
        {
            "run_id": "run_1",
            "goal_hash": "deadbeef",
            "ok": True,
            "paths": ["a.py", "b.py"],
            "reason": None,
        }
    )
    assert "run_1" not in summary
    assert "deadbeef" not in summary
    assert "是" in summary
    assert "a.py、b.py" in summary
    assert "原因：无" in summary
    items = event_summary(
        {
            "items": [
                {"name": "version", "status": "pass", "detail": "0.1.0"},
                {"name": "python", "status": "pass", "detail": "3.12"},
            ]
        }
    )
    assert "version 0.1.0" in items
    assert "python 3.12" in items


def test_unknown_future_event_gets_generic_human_title() -> None:
    assert event_title("some.future_event") == "状态更新"
    assert is_silent("model.requested") is True
    assert is_silent("run.failed") is False


def test_tool_copy_uses_action_target_status_and_duration() -> None:
    title = format_tool_title("list_directory", target=".", status="completed", duration_ms=12)
    body = format_tool_body(target=".", status="completed", duration_ms=12)
    assert title == "列出目录 · . · 完成 · 12ms"
    assert "目标：." in body
    assert "状态：完成" in body
    assert "耗时：12ms" in body
    assert "list_directory" not in title
    assert "tool.completed" not in title


def test_security_flag_is_visible_not_silent() -> None:
    projector = TimelineProjector()
    mutations = projector.apply(
        event("security.content_flagged", payload={"finding_count": 2, "source_kind": "web"})
    )
    appended = [item for item in mutations if isinstance(item, AppendBlock)]
    assert appended
    assert appended[0].block.title == "检测到可疑内容"
    assert "命中数：2" in appended[0].block.body


def test_recovery_inspection_copy_keeps_run_id_and_commands() -> None:
    body = format_recovery_inspection(
        "run_crash",
        {
            "run_id": "run_crash",
            "classification": "safe_to_abandon",
            "reason_code": "safe_to_abandon",
            "allowed_actions": ["abandon", "rerun"],
        },
    )
    assert "run-id：run_crash" in body
    assert "可安全放弃" in body
    assert "/abandon run_crash" in body
    assert "重新发起任务" in body
    assert "recovery.detected" not in body


def test_manual_required_inspection_does_not_loop_back_to_recover() -> None:
    body = format_recovery_inspection(
        "run_manual",
        {
            "run_id": "run_manual",
            "classification": "manual_required",
            "reason_code": "unknown_hash",
            "allowed_actions": ["inspect"],
            "evidence": [{"path": "notes.md", "state": "unknown"}],
        },
    )
    assert "run-id：run_manual" in body
    assert "不能自动 /resume 或 /abandon" in body
    assert "notes.md：unknown" in body
    assert "使用 /recover 查看分类后再 /resume 或 /abandon" not in body
