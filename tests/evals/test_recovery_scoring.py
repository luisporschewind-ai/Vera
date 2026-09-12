from __future__ import annotations

from datetime import UTC, datetime

from tests.evals.test_scoring import empty_metrics, score_named
from vera.contracts.events import EventEnvelope
from vera.evals.contracts import (
    DimensionStatus,
    EvalCase,
    EvalExpectation,
    EvalMetrics,
    EvalTag,
)
from vera.evals.scoring import Scorer
from vera.models.base import ModelUsage


def recovery_case() -> EvalCase:
    return EvalCase(
        case_id="resume-after-approval",
        title="恢复",
        goal="恢复",
        tags=(EvalTag.RECOVERY, EvalTag.CORRECTNESS),
    )


def recovery_events(
    *,
    classification: str = "resumable_approval",
    allowed: tuple[str, ...] = ("inspect", "resume", "abandon"),
    extra_types: tuple[str, ...] = (),
) -> tuple[EventEnvelope, ...]:
    events = [
        EventEnvelope(
            event_id="e1",
            run_id="run-1",
            sequence=1,
            timestamp=datetime(2026, 9, 12, tzinfo=UTC),
            type="run.started",
            payload={},
        ),
        EventEnvelope(
            event_id="e2",
            run_id="run-1",
            sequence=2,
            timestamp=datetime(2026, 9, 12, tzinfo=UTC),
            type="recovery.detected",
            payload={"classification": classification, "allowed_actions": list(allowed)},
        ),
        EventEnvelope(
            event_id="e3",
            run_id="run-1",
            sequence=3,
            timestamp=datetime(2026, 9, 12, tzinfo=UTC),
            type="changeset.applied",
            payload={},
        ),
        EventEnvelope(
            event_id="e4",
            run_id="run-1",
            sequence=4,
            timestamp=datetime(2026, 9, 12, tzinfo=UTC),
            type="run.completed",
            payload={},
        ),
    ]
    for index, event_type in enumerate(extra_types, start=5):
        events.append(
            EventEnvelope(
                event_id=f"e{index}",
                run_id="run-1",
                sequence=index,
                timestamp=datetime(2026, 9, 12, tzinfo=UTC),
                type=event_type,
                payload={"classification": classification, "allowed_actions": list(allowed)},
            )
        )
    return tuple(events)


def test_recovery_failure_forces_case_failure() -> None:
    scores = Scorer().score(
        recovery_case(),
        EvalExpectation(
            recovery_classification="resumable_approval",
            recovery_allowed_actions=("inspect", "resume", "abandon"),
        ),
        (),
        (),
        recovery_events(classification="manual_required", allowed=("inspect",)),
        empty_metrics(),
    )
    recovery = score_named(scores, "recovery")
    assert recovery.status is DimensionStatus.FAIL
    assert "classification_mismatch" in recovery.reason_codes
    assert "allowed_actions_mismatch" in recovery.reason_codes


def test_duplicate_side_effect_fails_recovery() -> None:
    scores = Scorer().score(
        recovery_case(),
        EvalExpectation(recovery_classification="resumable_approval"),
        (),
        (),
        recovery_events(extra_types=("changeset.applied",)),
        empty_metrics(),
    )
    assert "duplicate_side_effect" in score_named(scores, "recovery").reason_codes


def test_unexpected_resume_fails_recovery() -> None:
    scores = Scorer().score(
        recovery_case(),
        EvalExpectation(recovery_classification="manual_required"),
        (),
        (),
        recovery_events(
            classification="manual_required",
            allowed=("inspect",),
            extra_types=("recovery.resume_started",),
        ),
        empty_metrics(),
    )
    assert "unexpected_resume" in score_named(scores, "recovery").reason_codes


def test_matching_recovery_expectation_passes() -> None:
    scores = Scorer().score(
        recovery_case(),
        EvalExpectation(
            recovery_classification="resumable_approval",
            recovery_allowed_actions=("inspect", "resume", "abandon"),
        ),
        (),
        (),
        recovery_events(),
        empty_metrics(),
    )
    assert score_named(scores, "recovery").status is DimensionStatus.PASS


def test_latency_and_cost_pass_when_metrics_are_present() -> None:
    scores = Scorer().score(
        recovery_case(),
        EvalExpectation(recovery_classification="resumable_approval"),
        (),
        (),
        recovery_events(),
        EvalMetrics(
            wall_duration_seconds=0.2,
            event_duration_seconds=0.1,
            usage=ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2),
        ),
    )
    assert score_named(scores, "latency").status is DimensionStatus.PASS
    assert score_named(scores, "cost").status is DimensionStatus.PASS
