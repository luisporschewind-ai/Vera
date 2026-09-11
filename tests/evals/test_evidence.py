from __future__ import annotations

import json
from pathlib import Path

import pytest

from vera.evals.contracts import (
    DimensionStatus,
    EvalMetrics,
    EvalReport,
    EvalScore,
    EvalStatus,
    EvalWorkerResult,
    FileFact,
)
from vera.evals.evidence import EvidenceError, EvidenceWriter


def _result(tmp_path: Path) -> EvalWorkerResult:
    report = EvalReport(
        evaluation_id="eval-abc",
        case_id="plain-answer",
        status=EvalStatus.PASS,
        scores=(EvalScore(dimension="correctness", status=DimensionStatus.PASS),),
        event_types=("run.completed",),
        after_files=(FileFact(path="README.md", kind="file", size=8, sha256="a" * 64),),
        metrics=EvalMetrics(),
    )
    return EvalWorkerResult(report=report, after_files=report.after_files)


def test_evidence_writer_never_overwrites_existing_directory(tmp_path: Path) -> None:
    result = _result(tmp_path)
    existing = tmp_path / result.report.evaluation_id
    existing.mkdir()
    with pytest.raises(EvidenceError, match="output_exists"):
        EvidenceWriter().publish(result, tmp_path)


def test_evidence_writer_publishes_private_files(tmp_path: Path) -> None:
    result = _result(tmp_path)
    published = EvidenceWriter().publish(result, tmp_path)
    assert published.name == "eval-abc"
    assert (published / "report.json").is_file()
    files = json.loads((published / "files.json").read_text(encoding="utf-8"))
    assert "after_files" in files
    assert files["after_files"][0]["path"] == "README.md"
    assert "after_content" not in (published / "report.json").read_text(encoding="utf-8")
    events = (published / "events.jsonl").read_text(encoding="utf-8")
    assert events == "" or events.endswith("\n") or events == ""
