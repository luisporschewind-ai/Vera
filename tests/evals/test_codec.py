import json
from pathlib import Path

import pytest

from vera.evals.codec import EvalCodec, EvalCodecError
from vera.evals.contracts import (
    DimensionStatus,
    EvalCase,
    EvalExpectation,
    EvalFileExpectation,
    EvalMetrics,
    EvalReport,
    EvalScore,
    EvalScript,
    EvalStatus,
    EvalSuiteReport,
    EvalTag,
    EvalWorkerRequest,
    EvalWorkerResult,
    FileFact,
)
from vera.models.base import ModelTurn, ModelUsage


def _report() -> EvalReport:
    return EvalReport(
        evaluation_id="eval-random",
        case_id="create-file",
        status=EvalStatus.PASS,
        scores=(
            EvalScore(dimension="safety", status=DimensionStatus.PASS, reason_codes=()),
            EvalScore(dimension="correctness", status=DimensionStatus.PASS),
        ),
        reason_codes=("ok",),
        run_ids=("run-z", "run-a"),
        event_types=("run.started", "run.completed"),
        before_files=(FileFact(path="b.txt", kind="file", size=1, sha256="b" * 64),),
        after_files=(FileFact(path="a.txt", kind="file", size=2, sha256="a" * 64),),
        metrics=EvalMetrics(
            wall_duration_seconds=1.25,
            event_duration_seconds=0.4,
            usage=ModelUsage(input_tokens=1, output_tokens=2, total_tokens=3),
        ),
    )


def test_codec_rejects_future_schema_without_partial_decode() -> None:
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_case('{"schema_version":2,"case_id":"x"}', source="case.json")
    assert caught.value.code == "unsupported_schema"
    assert caught.value.source == "case.json"
    assert '{"schema_version"' not in caught.value.message


def test_codec_rejects_invalid_utf8_and_non_object() -> None:
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_case(b"\xff\xfe", source="case.json")
    assert caught.value.code == "invalid_json"
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_script("[]", source="script.json")
    assert caught.value.code == "invalid_json"
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_expectation("not-json", source="expect.json")
    assert caught.value.code == "invalid_json"
    assert "not-json" not in caught.value.message


def test_codec_rejects_extra_fields_on_case() -> None:
    payload = {
        "schema_version": 1,
        "case_id": "plain-answer",
        "title": "普通回答",
        "goal": "回答问题",
        "tags": ["conversation"],
        "model": "fake",
        "timeout_seconds": 10,
        "scenario": "standard",
        "live": True,
    }
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_case(json.dumps(payload), source="case.json")
    assert caught.value.code == "invalid_contract"


def test_codec_round_trips_known_payloads(tmp_path: Path) -> None:
    case = EvalCase(
        case_id="plain-answer",
        title="普通回答",
        goal="回答问题",
        tags=(EvalTag.CONVERSATION,),
    )
    script = EvalScript(turns=(ModelTurn(assistant_text="ok", finish_reason="stop"),))
    expect = EvalExpectation(
        files=(EvalFileExpectation(path="README.md", sha256="c" * 64),),
        allowed_changed_paths=(),
        required_event_types=("assistant.message", "run.completed"),
        terminal_event="run.completed",
    )
    request = EvalWorkerRequest(
        evaluation_id="eval-1",
        case_id="plain-answer",
        corpus_root=tmp_path / "corpus",
        workspace=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        staging_dir=tmp_path / "staging",
    )
    result = EvalWorkerResult(report=_report())
    assert EvalCodec.decode_case(case.model_dump_json()) == case
    assert EvalCodec.decode_script(script.model_dump_json()) == script
    assert EvalCodec.decode_expectation(expect.model_dump_json()) == expect
    assert EvalCodec.decode_worker_request(request.model_dump_json()) == request
    assert EvalCodec.decode_worker_result(result.model_dump_json()) == result


def test_canonical_report_excludes_nondeterministic_fields() -> None:
    canonical = EvalCodec.canonical_report(_report())
    assert "evaluation_id" not in canonical
    assert "run_ids" not in canonical
    assert "wall_duration_seconds" not in canonical["metrics"]
    assert "event_duration_seconds" not in canonical["metrics"]
    assert list(canonical.keys()) == [
        "after_files",
        "before_files",
        "case_id",
        "event_types",
        "metrics",
        "reason_codes",
        "scores",
        "status",
    ]
    assert canonical["metrics"]["usage"] == {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
    }


def test_canonical_report_includes_reported_cache_facts() -> None:
    report = _report()
    metrics = report.metrics.model_copy(
        update={
            "usage": ModelUsage(
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
                cache_hit_input_tokens=6,
                cache_miss_input_tokens=4,
            )
        }
    )
    report = report.model_copy(update={"metrics": metrics})
    usage = EvalCodec.canonical_report(report)["metrics"]["usage"]
    assert usage == {
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
        "cache_hit_input_tokens": 6,
        "cache_miss_input_tokens": 4,
    }


def test_canonical_report_encodes_missing_usage_as_null() -> None:
    report = _report()
    report = report.model_copy(update={"metrics": EvalMetrics()})
    canonical = EvalCodec.canonical_report(report)
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    assert '"usage": null' in encoded


def test_encode_report_uses_stable_utf8_and_null_usage() -> None:
    encoded_report = EvalCodec.encode_report(
        _report().model_copy(update={"metrics": EvalMetrics()})
    )
    payload = json.loads(encoded_report)
    assert payload["metrics"]["usage"] is None
    suite = EvalSuiteReport(evaluation_id="suite-1", status=EvalStatus.PASS, cases=(_report(),))
    encoded = EvalCodec.encode_suite_report(suite)
    parsed = json.loads(encoded)
    assert parsed["cases"][0]["case_id"] == "create-file"


def test_codec_rejects_worker_result_pass_with_error() -> None:
    payload = EvalWorkerResult(report=_report()).model_dump(mode="json")
    payload["error_code"] = "runtime_exception"
    with pytest.raises(EvalCodecError) as caught:
        EvalCodec.decode_worker_result(json.dumps(payload), source="result.json")
    assert caught.value.code == "invalid_contract"
    assert "runtime_exception" in caught.value.message or caught.value.source == "result.json"
