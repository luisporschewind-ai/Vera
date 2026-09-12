from __future__ import annotations

from vera.evals.contracts import (
    DimensionStatus,
    EvalMetrics,
    EvalReport,
    EvalScore,
    EvalStatus,
    EvalSuiteReport,
    FileFact,
)
from vera.evals.determinism import CanonicalComparator
from vera.models.base import ModelUsage


def _report(
    *,
    evaluation_id: str = "eval-a",
    case_id: str = "create-file",
    run_ids: tuple[str, ...] = ("run-a",),
    event_types: tuple[str, ...] = ("run.started", "run.completed"),
    reason_codes: tuple[str, ...] = (),
    sha256: str = "a" * 64,
    usage: ModelUsage | None = None,
) -> EvalReport:
    return EvalReport(
        evaluation_id=evaluation_id,
        case_id=case_id,
        status=EvalStatus.PASS,
        scores=(EvalScore(dimension="correctness", status=DimensionStatus.PASS),),
        reason_codes=reason_codes,
        run_ids=run_ids,
        event_types=event_types,
        after_files=(FileFact(path="hello.txt", kind="file", size=1, sha256=sha256),),
        metrics=EvalMetrics(
            wall_duration_seconds=1.25,
            event_duration_seconds=0.4,
            usage=usage or ModelUsage(input_tokens=1, output_tokens=2, total_tokens=3),
        ),
    )


def test_canonical_comparison_ignores_ids_but_not_event_order() -> None:
    first = _report(
        evaluation_id="a",
        run_ids=("run_a",),
        event_types=("run.started", "run.completed"),
    )
    second = _report(
        evaluation_id="b",
        run_ids=("run_b",),
        event_types=("run.completed", "run.started"),
    )
    assert CanonicalComparator().compare(first, second).equal is False


def test_canonical_comparison_ignores_ids_and_durations() -> None:
    first = _report(evaluation_id="a", run_ids=("run_a",))
    second = _report(evaluation_id="b", run_ids=("run_b",))
    assert CanonicalComparator().compare(first, second).equal is True


def test_canonical_comparison_keeps_hash_reason_and_usage_differences() -> None:
    base = _report()
    hash_diff = CanonicalComparator().compare(base, _report(sha256="b" * 64))
    assert hash_diff.equal is False
    reason_diff = CanonicalComparator().compare(base, _report(reason_codes=("file_hash_mismatch",)))
    assert reason_diff.equal is False
    usage_diff = CanonicalComparator().compare(
        base,
        _report(usage=ModelUsage(input_tokens=9, output_tokens=2, total_tokens=11)),
    )
    assert usage_diff.equal is False


def test_suite_comparison_aligns_by_case_id() -> None:
    first = EvalSuiteReport(
        evaluation_id="suite-a",
        status=EvalStatus.PASS,
        cases=(_report(case_id="create-file"), _report(case_id="plain-answer")),
    )
    second = EvalSuiteReport(
        evaluation_id="suite-b",
        status=EvalStatus.FAIL,
        cases=(_report(case_id="plain-answer"),),
    )
    result = CanonicalComparator().compare(first, second)
    assert result.equal is False
    assert "missing:create-file" in result.differences
