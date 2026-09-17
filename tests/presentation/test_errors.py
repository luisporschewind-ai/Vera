from datetime import UTC, datetime

from vera.contracts.events import EventEnvelope
from vera.presentation.errors import (
    describe_reason,
    explain_failure,
    format_diagnostics,
    format_failure_body,
)
from vera.presentation.projector import TimelineProjector


def event(event_type: str, *, sequence: int = 1, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"e{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp=datetime.now(UTC),
        type=event_type,
        payload=payload or {},
    )


def test_read_only_failure_does_not_claim_workspace_changes() -> None:
    explained = explain_failure(
        event("run.failed", payload={"reason": "model_error"}),
        side_effects="no_workspace_change",
    )
    assert "未产生工作区变化" in explained["side_effects"]
    assert "可能" not in explained["side_effects"]
    assert "回滚" not in explained["next"]


def test_written_failure_points_at_diff_and_rollback() -> None:
    explained = explain_failure(
        event("run.failed", payload={"reason": "write_failed"}),
        side_effects="workspace_changed",
    )
    assert "已写入工作区变更" in explained["side_effects"]
    assert "/rollback" in explained["next"]


def test_unknown_side_effects_stays_conservative() -> None:
    explained = explain_failure(event("run.failed", payload={"reason": "model_error"}))
    assert "可能" in explained["side_effects"]


def test_reason_codes_are_translated_but_still_visible() -> None:
    assert "模型调用失败" in describe_reason("model_error")
    assert "model_error" in describe_reason("model_error")
    assert "创建检查点失败" in describe_reason("checkpoint_failed:disk full")
    assert "没有写入权限" in describe_reason("permission_denied")
    assert "permission_denied" in describe_reason("permission_denied")
    assert describe_reason("something_new") == "something_new"


def test_provider_diagnostics_are_surfaced() -> None:
    detail = format_diagnostics(
        {
            "code": "provider_request_invalid",
            "status_code": 400,
            "detail": "context length exceeded",
            "retry_after_seconds": None,
        }
    )
    assert "HTTP 400" in detail
    assert "context length exceeded" in detail
    assert format_diagnostics(None) == ""


def test_projector_derives_side_effects_from_observed_events() -> None:
    read_only = TimelineProjector()
    read_only.apply(event("tool.completed", payload={"name": "read_file", "ok": True}))
    mutations = read_only.apply(event("run.failed", sequence=2, payload={"reason": "model_error"}))
    body = mutations[0].block.body  # type: ignore[union-attr]
    assert "未产生工作区变化" in body

    wrote = TimelineProjector()
    wrote.apply(event("changeset.applied", payload={"status": "applied"}))
    written_mutations = wrote.apply(
        event("run.failed", sequence=2, payload={"reason": "write_failed"})
    )
    written_body = written_mutations[0].block.body  # type: ignore[union-attr]
    assert "已写入工作区变更" in written_body


def test_model_failure_detail_reaches_the_failure_card() -> None:
    projector = TimelineProjector()
    projector.apply(
        event(
            "model.failed",
            payload={
                "code": "provider_request_invalid",
                "status_code": 400,
                "detail": "context length exceeded",
            },
        )
    )
    mutations = projector.apply(event("run.failed", sequence=2, payload={"reason": "model_error"}))
    body = mutations[0].block.body  # type: ignore[union-attr]
    assert "诊断：" in body
    assert "HTTP 400" in body
    assert "context length exceeded" in body
    assert "未产生工作区变化" in body


def test_cancel_without_writes_says_nothing_to_roll_back() -> None:
    body = format_failure_body(event("run.cancelled"), side_effects="no_workspace_change")
    assert "未产生工作区变化" in body
    assert "/rollback" not in body


def test_recovery_failure_uses_reason_code() -> None:
    body = format_failure_body(
        event("recovery.manual_required", payload={"reason_code": "invalid_snapshot"})
    )
    assert "原因未记录" not in body
    assert "快照无效或损坏" in body
    assert "invalid_snapshot" in body
    assert "不允许 /resume 或 /abandon" in body
    assert "使用 /recover 查看分类" not in body
