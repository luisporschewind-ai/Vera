from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vera.contracts.events import EventEnvelope
from vera.evals.contracts import (
    DimensionStatus,
    EvalCase,
    EvalExpectation,
    EvalFileExpectation,
    EvalMetrics,
    EvalReport,
    EvalScenario,
    EvalScore,
    EvalScript,
    EvalStatus,
    EvalSuiteReport,
    EvalTag,
    EvalWorkerRequest,
    EvalWorkerResult,
    FileFact,
)
from vera.models.base import ModelTurn


def _case(**overrides: object) -> EvalCase:
    payload: dict[str, object] = {
        "case_id": "create-file",
        "title": "创建文件",
        "goal": "创建 hello.txt",
        "tags": (EvalTag.CORRECTNESS,),
        "model": "fake",
        "timeout_seconds": 30,
        "scenario": EvalScenario.STANDARD,
    }
    payload.update(overrides)
    return EvalCase.model_validate(payload)


def _report(**overrides: object) -> EvalReport:
    payload: dict[str, object] = {
        "evaluation_id": "eval-1",
        "case_id": "create-file",
        "status": EvalStatus.PASS,
        "scores": (
            EvalScore(dimension="correctness", status=DimensionStatus.PASS),
            EvalScore(dimension="safety", status=DimensionStatus.PASS),
        ),
        "reason_codes": (),
        "run_ids": ("run-1",),
        "event_types": ("run.started", "run.completed"),
        "before_files": (),
        "after_files": (FileFact(path="hello.txt", kind="file", size=6, sha256="a" * 64),),
        "metrics": EvalMetrics(),
    }
    payload.update(overrides)
    return EvalReport.model_validate(payload)


def test_eval_case_round_trips_and_forbids_live() -> None:
    case = _case()
    assert EvalCase.model_validate_json(case.model_dump_json()) == case
    with pytest.raises(ValidationError):
        EvalCase.model_validate({**case.model_dump(), "model": "live"})


@pytest.mark.parametrize(
    "case_id",
    ["CreateFile", "create_file", "", "create--file", "-create", "create-"],
)
def test_eval_case_rejects_illegal_case_id(case_id: str) -> None:
    with pytest.raises(ValidationError):
        _case(case_id=case_id)


def test_eval_case_rejects_duplicate_tags() -> None:
    with pytest.raises(ValidationError):
        _case(tags=(EvalTag.CORRECTNESS, EvalTag.CORRECTNESS))


@pytest.mark.parametrize("timeout_seconds", [0, 121])
def test_eval_case_rejects_timeout_outside_range(timeout_seconds: int) -> None:
    with pytest.raises(ValidationError):
        _case(timeout_seconds=timeout_seconds)


def test_eval_case_rejects_unknown_scenario() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate({**_case().model_dump(), "scenario": "live-provider"})


def test_eval_script_round_trips_known_turns_and_approvals() -> None:
    script = EvalScript(
        turns=(ModelTurn(assistant_text="done", finish_reason="stop"),),
        text_deltas=(("hello", " world"),),
        approvals=("approve", "reject", "cancel"),
    )
    assert EvalScript.model_validate_json(script.model_dump_json()) == script


def test_eval_script_rejects_unknown_approval() -> None:
    with pytest.raises(ValidationError):
        EvalScript.model_validate({"turns": [], "approvals": ["maybe"]})


def test_expectation_rejects_absolute_and_parent_paths() -> None:
    with pytest.raises(ValidationError):
        EvalFileExpectation(path="/tmp/hello.txt", exists=True, sha256="a" * 64)
    with pytest.raises(ValidationError):
        EvalFileExpectation(path="../outside.txt", exists=True, sha256="a" * 64)
    with pytest.raises(ValidationError):
        EvalExpectation(allowed_changed_paths=("/abs/path",))
    with pytest.raises(ValidationError):
        EvalExpectation(allowed_changed_paths=("ok.txt", "ok.txt"))


def test_usage_missing_stays_none() -> None:
    metrics = EvalMetrics()
    assert metrics.usage is None
    encoded = metrics.model_dump(mode="json")
    assert encoded["usage"] is None
    restored = EvalMetrics.model_validate({"usage": None})
    assert restored.usage is None


def test_report_rejects_empty_scores_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _report(scores=())
    with pytest.raises(ValidationError):
        EvalReport.model_validate({**_report().model_dump(), "prompt": "nope"})


def test_worker_request_requires_absolute_controlled_paths(tmp_path) -> None:
    request = EvalWorkerRequest(
        evaluation_id="eval-1",
        case_id="create-file",
        corpus_root=tmp_path / "corpus",
        workspace=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        staging_dir=tmp_path / "staging",
    )
    assert EvalWorkerRequest.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError):
        EvalWorkerRequest(
            evaluation_id="eval-1",
            case_id="create-file",
            corpus_root=tmp_path / "corpus",
            workspace="workspace",
            state_dir=tmp_path / "state",
            staging_dir=tmp_path / "staging",
        )


def test_worker_result_cannot_claim_pass_with_error_code() -> None:
    report = _report()
    with pytest.raises(ValidationError):
        EvalWorkerResult(error_code="runtime_exception", report=report)
    failed = EvalWorkerResult(
        error_code="runtime_exception",
        report=_report(
            status=EvalStatus.ERROR,
            scores=(EvalScore(dimension="correctness", status=DimensionStatus.FAIL),),
        ),
        events=(
            EventEnvelope(
                event_id="e1",
                run_id="run-1",
                sequence=1,
                timestamp=datetime(2026, 9, 12, tzinfo=UTC),
                type="run.failed",
                payload={},
            ),
        ),
    )
    assert failed.report is not None
    assert failed.report.status is EvalStatus.ERROR


def test_suite_report_lookup_and_sorted_cases() -> None:
    first = _report(case_id="create-file")
    second = _report(case_id="plain-answer", evaluation_id="eval-2")
    suite = EvalSuiteReport(evaluation_id="suite-1", status=EvalStatus.PASS, cases=(second, first))
    assert [item.case_id for item in suite.cases] == ["create-file", "plain-answer"]
    assert suite.case("plain-answer") is suite.cases[1]
    with pytest.raises(KeyError):
        suite.case("missing")
