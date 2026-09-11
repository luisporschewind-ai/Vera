"""Explicit JSON codecs for evaluation contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from vera.evals.contracts import (
    EvalCase,
    EvalContract,
    EvalExpectation,
    EvalReport,
    EvalScript,
    EvalSuiteReport,
    EvalWorkerRequest,
    EvalWorkerResult,
)

_CANONICAL_REPORT_KEYS = (
    "after_files",
    "before_files",
    "case_id",
    "event_types",
    "metrics",
    "reason_codes",
    "scores",
    "status",
)


class EvalCodecError(ValueError):
    def __init__(self, code: str, source: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.source = source
        self.message = message


class EvalCodec:
    @staticmethod
    def decode_case(data: str | bytes, *, source: str = "case.json") -> EvalCase:
        return _decode(EvalCase, data, source)

    @staticmethod
    def decode_script(data: str | bytes, *, source: str = "script.json") -> EvalScript:
        return _decode(EvalScript, data, source)

    @staticmethod
    def decode_expectation(data: str | bytes, *, source: str = "expect.json") -> EvalExpectation:
        return _decode(EvalExpectation, data, source)

    @staticmethod
    def decode_worker_request(
        data: str | bytes, *, source: str = "request.json"
    ) -> EvalWorkerRequest:
        return _decode(EvalWorkerRequest, data, source)

    @staticmethod
    def decode_worker_result(
        data: str | bytes, *, source: str = "result.json"
    ) -> EvalWorkerResult:
        return _decode(EvalWorkerResult, data, source)

    @staticmethod
    def encode_report(report: EvalReport) -> str:
        return _encode(report)

    @staticmethod
    def encode_suite_report(report: EvalSuiteReport) -> str:
        return _encode(report)

    @staticmethod
    def canonical_report(report: EvalReport) -> dict[str, Any]:
        payload = report.model_dump(mode="json")
        metrics = payload.get("metrics") or {}
        usage = metrics.get("usage")
        canonical = {
            "after_files": payload.get("after_files") or [],
            "before_files": payload.get("before_files") or [],
            "case_id": payload["case_id"],
            "event_types": payload.get("event_types") or [],
            "metrics": {"usage": usage},
            "reason_codes": payload.get("reason_codes") or [],
            "scores": payload.get("scores") or [],
            "status": payload["status"],
        }
        return _sorted_mapping({key: canonical[key] for key in _CANONICAL_REPORT_KEYS})


def _decode[T: EvalContract](model: type[T], data: str | bytes, source: str) -> T:
    payload = _load_object(data, source)
    version = payload.get("schema_version")
    if version != 1:
        raise EvalCodecError(
            "unsupported_schema",
            source,
            f"unsupported schema_version for {source}",
        )
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise EvalCodecError("invalid_contract", source, f"invalid {source}") from exc


def _load_object(data: str | bytes, source: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        payload = json.loads(text)
    except UnicodeDecodeError as exc:
        raise EvalCodecError("invalid_json", source, f"invalid utf-8 in {source}") from exc
    except json.JSONDecodeError as exc:
        raise EvalCodecError("invalid_json", source, f"invalid json in {source}") from exc
    if not isinstance(payload, dict):
        raise EvalCodecError("invalid_json", source, f"{source} must be a json object")
    return payload


def _encode(model: EvalContract) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _sorted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _sorted_value(value[key]) for key in sorted(value)}


def _sorted_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _sorted_mapping(value)
    if isinstance(value, list):
        return [_sorted_value(item) for item in value]
    return value
