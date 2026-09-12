"""Redacted dogfood log schema. Never records source, prompts, or secrets."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from vera.contracts import ContractModel

DOGFOOD_SCHEMA_VERSION = 1
PROJECT_KINDS = ("swift", "python", "node")
RESULTS = ("pass", "fail", "blocked")
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|-----BEGIN |api[_-]?key\s*[:=]|ghp_[A-Za-z0-9]+|xox[baprs]-)",
    re.IGNORECASE,
)
_FORBIDDEN_KEYS = frozenset(
    {
        "source",
        "request",
        "prompt",
        "goal",
        "diff",
        "content",
        "body",
        "token",
        "api_key",
        "secret",
    }
)


class DogfoodError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DogfoodEntry(ContractModel):
    schema_version: Literal[1] = 1
    index: int
    recorded_at: datetime
    project_kind: Literal["swift", "python", "node"]
    workflow: str
    result: Literal["pass", "fail", "blocked"]
    failure_class: str | None = None
    recovery: str | None = None
    metrics: dict[str, int | float | str] = {}


class DogfoodLog(ContractModel):
    schema_version: Literal[1] = 1
    entries: tuple[DogfoodEntry, ...] = ()

    @property
    def completed_count(self) -> int:
        return len(self.entries)


def _reject_secrets(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _FORBIDDEN_KEYS:
                raise DogfoodError("forbidden_field", f"dogfood log must not include {path}.{key}")
            _reject_secrets(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secrets(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _SECRET.search(value):
        raise DogfoodError("secret_payload", f"dogfood log must not include secrets in {path}")


def validate_dogfood_log(payload: dict[str, object] | str | bytes) -> DogfoodLog:
    if isinstance(payload, (str, bytes)):
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise DogfoodError("invalid_json", "dogfood log is not valid json") from exc
    else:
        loaded = payload
    if not isinstance(loaded, dict):
        raise DogfoodError("invalid_json", "dogfood log must be an object")
    if loaded.get("schema_version") != DOGFOOD_SCHEMA_VERSION:
        raise DogfoodError("unsupported_schema", "unsupported dogfood schema_version")
    if "entries" not in loaded:
        raise DogfoodError("missing_field", "dogfood log requires entries")
    _reject_secrets(loaded, path="log")
    try:
        log = DogfoodLog.model_validate(loaded)
    except Exception as exc:
        raise DogfoodError("invalid_contract", "dogfood log failed schema validation") from exc
    seen: set[int] = set()
    for entry in log.entries:
        if entry.index in seen:
            raise DogfoodError("duplicate_index", f"duplicate dogfood index {entry.index}")
        seen.add(entry.index)
        if entry.index < 1:
            raise DogfoodError("invalid_index", "dogfood index must start at 1")
        if entry.result == "pass" and entry.failure_class:
            raise DogfoodError("invalid_result", "passing entries cannot carry a failure_class")
        if entry.result != "pass" and not entry.failure_class:
            raise DogfoodError("missing_field", "failed entries require failure_class")
    return log


def load_dogfood_log(path: Path) -> DogfoodLog:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DogfoodError("unreadable", f"cannot read dogfood log: {path}") from exc
    return validate_dogfood_log(text)


def example_offline_log() -> DogfoodLog:
    return DogfoodLog(
        entries=(
            DogfoodEntry(
                index=1,
                recorded_at=datetime.fromisoformat("2026-09-13T00:00:00+00:00"),
                project_kind="python",
                workflow="readonly-then-edit",
                result="pass",
                metrics={"duration_seconds": 12},
            ),
        )
    )


def summarize_dogfood(log: DogfoodLog) -> dict[str, object]:
    results = {kind: 0 for kind in RESULTS}
    for entry in log.entries:
        results[entry.result] += 1
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "count": log.completed_count,
        "results": results,
        "user_completed_20": False,
    }
