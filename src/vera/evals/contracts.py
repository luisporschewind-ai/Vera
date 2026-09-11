"""Versioned, frozen contracts for the offline evaluation client."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from vera.contracts import ContractModel
from vera.contracts.events import EventEnvelope
from vera.models.base import ModelTurn, ModelUsage

SHA256_HEX = r"^[0-9a-f]{64}$"
CASE_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class EvalContract(ContractModel):
    """Common immutability and extra-field policy for evaluation schemas."""


class EvalTag(StrEnum):
    CORRECTNESS = "correctness"
    SAFETY = "safety"
    RECOVERY = "recovery"
    CONVERSATION = "conversation"


class EvalScenario(StrEnum):
    STANDARD = "standard"
    ROLLBACK = "rollback"
    RESUME_AFTER_APPROVAL = "resume-after-approval"
    RESTORE_PARTIAL_APPLY = "restore-partial-apply"
    IN_FLIGHT_MANUAL = "in-flight-manual"
    IDEMPOTENT_RESUME = "idempotent-resume"


class EvalStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    TIMEOUT = "timeout"


class DimensionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class EvalDimension(StrEnum):
    CORRECTNESS = "correctness"
    SAFETY = "safety"
    RECOVERY = "recovery"
    LATENCY = "latency"
    COST = "cost"


class FileKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


def reject_eval_relative_path(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("path must not be empty")
    path = Path(candidate)
    if path.is_absolute() or candidate.startswith("/") or candidate.startswith("~"):
        raise ValueError("path must be relative")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must not contain '.' or '..'")
    if "\\" in candidate:
        raise ValueError("path must use posix separators")
    return candidate


class EvalCase(EvalContract):
    schema_version: Literal[1] = 1
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=2_000)
    tags: tuple[EvalTag, ...] = Field(min_length=1)
    model: Literal["fake"] = "fake"
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    scenario: EvalScenario = EvalScenario.STANDARD

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: tuple[EvalTag, ...]) -> tuple[EvalTag, ...]:
        if len(set(value)) != len(value):
            raise ValueError("tags must be unique")
        return value


class EvalScript(EvalContract):
    schema_version: Literal[1] = 1
    turns: tuple[ModelTurn, ...] = ()
    text_deltas: tuple[tuple[str, ...], ...] = ()
    approvals: tuple[Literal["approve", "reject", "cancel"], ...] = ()


class EvalFileExpectation(EvalContract):
    path: str
    exists: bool = True
    kind: FileKind = FileKind.FILE
    sha256: str | None = Field(default=None, pattern=SHA256_HEX)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        return reject_eval_relative_path(value)

    @model_validator(mode="after")
    def hash_matches_existence(self) -> Self:
        if self.exists and self.kind is FileKind.FILE and self.sha256 is None:
            raise ValueError("existing files require sha256")
        if (not self.exists or self.kind is FileKind.DIRECTORY) and self.sha256 is not None:
            raise ValueError("sha256 is only valid for existing files")
        return self


class EvalExpectation(EvalContract):
    schema_version: Literal[1] = 1
    files: tuple[EvalFileExpectation, ...] = ()
    allowed_changed_paths: tuple[str, ...] = ()
    required_event_types: tuple[str, ...] = ()
    forbidden_event_types: tuple[str, ...] = ()
    terminal_event: str | None = None
    recovery_classification: str | None = None
    recovery_allowed_actions: tuple[str, ...] = ()

    @field_validator("allowed_changed_paths")
    @classmethod
    def unique_relative_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(reject_eval_relative_path(item) for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_changed_paths must be unique")
        return normalized

    @field_validator("files")
    @classmethod
    def unique_file_paths(
        cls, value: tuple[EvalFileExpectation, ...]
    ) -> tuple[EvalFileExpectation, ...]:
        paths = tuple(item.path for item in value)
        if len(set(paths)) != len(paths):
            raise ValueError("expectation files must have unique paths")
        return value


class FileFact(EvalContract):
    path: str
    kind: FileKind
    size: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=SHA256_HEX)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        return reject_eval_relative_path(value)

    @model_validator(mode="after")
    def kind_matches_hash(self) -> Self:
        if self.kind is FileKind.FILE:
            if self.size is None or self.sha256 is None:
                raise ValueError("file facts require size and sha256")
        elif self.sha256 is not None:
            raise ValueError("directories must not include sha256")
        return self


class EvalMetrics(EvalContract):
    wall_duration_seconds: float | None = Field(default=None, ge=0)
    event_duration_seconds: float | None = Field(default=None, ge=0)
    usage: ModelUsage | None = None


class EvalScore(EvalContract):
    dimension: EvalDimension
    status: DimensionStatus
    reason_codes: tuple[str, ...] = ()

    @field_validator("reason_codes")
    @classmethod
    def unique_sorted_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError("reason_codes must be non-empty strings")
        if len(set(value)) != len(value):
            raise ValueError("reason_codes must be unique")
        return tuple(sorted(value))


class EvalReport(EvalContract):
    schema_version: Literal[1] = 1
    evaluation_id: str = Field(min_length=1)
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    status: EvalStatus
    scores: tuple[EvalScore, ...] = Field(min_length=1)
    reason_codes: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    before_files: tuple[FileFact, ...] = ()
    after_files: tuple[FileFact, ...] = ()
    metrics: EvalMetrics = Field(default_factory=EvalMetrics)

    @field_validator("reason_codes")
    @classmethod
    def unique_sorted_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError("reason_codes must be non-empty strings")
        if len(set(value)) != len(value):
            raise ValueError("reason_codes must be unique")
        return tuple(sorted(value))

    @field_validator("scores")
    @classmethod
    def unique_dimensions(cls, value: tuple[EvalScore, ...]) -> tuple[EvalScore, ...]:
        names = tuple(item.dimension for item in value)
        if len(set(names)) != len(names):
            raise ValueError("scores must have unique dimensions")
        return tuple(sorted(value, key=lambda item: item.dimension.value))

    @field_validator("before_files", "after_files")
    @classmethod
    def sorted_unique_files(cls, value: tuple[FileFact, ...]) -> tuple[FileFact, ...]:
        paths = tuple(item.path for item in value)
        if len(set(paths)) != len(paths):
            raise ValueError("file facts must have unique paths")
        return tuple(sorted(value, key=lambda item: item.path))


class EvalSuiteReport(EvalContract):
    schema_version: Literal[1] = 1
    evaluation_id: str = Field(min_length=1)
    status: EvalStatus
    cases: tuple[EvalReport, ...] = ()

    @field_validator("cases")
    @classmethod
    def sorted_unique_cases(cls, value: tuple[EvalReport, ...]) -> tuple[EvalReport, ...]:
        ids = tuple(item.case_id for item in value)
        if len(set(ids)) != len(ids):
            raise ValueError("suite cases must have unique case_id")
        return tuple(sorted(value, key=lambda item: item.case_id))

    def case(self, case_id: str) -> EvalReport:
        for item in self.cases:
            if item.case_id == case_id:
                return item
        raise KeyError(case_id)


class EvalWorkerRequest(EvalContract):
    schema_version: Literal[1] = 1
    evaluation_id: str = Field(min_length=1)
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    corpus_root: Path
    workspace: Path
    state_dir: Path
    staging_dir: Path

    @field_validator("corpus_root", "workspace", "state_dir", "staging_dir")
    @classmethod
    def absolute_paths(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("worker paths must be absolute")
        return value


class EvalWorkerResult(EvalContract):
    schema_version: Literal[1] = 1
    error_code: str | None = None
    report: EvalReport | None = None
    events: tuple[EventEnvelope, ...] = ()
    before_files: tuple[FileFact, ...] = ()
    after_files: tuple[FileFact, ...] = ()

    @model_validator(mode="after")
    def pass_requires_no_error(self) -> Self:
        if self.error_code and self.report is not None and self.report.status is EvalStatus.PASS:
            raise ValueError("worker result cannot claim pass with an error_code")
        if self.error_code is None and self.report is None:
            raise ValueError("successful worker result requires a report")
        return self
