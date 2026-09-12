from __future__ import annotations

import json
import stat
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


def test_evidence_writer_preserves_existing_output_root_mode(tmp_path: Path) -> None:
    result = _result(tmp_path)
    tmp_path.chmod(0o755)
    before = stat.S_IMODE(tmp_path.stat().st_mode)
    EvidenceWriter().publish(result, tmp_path)
    assert stat.S_IMODE(tmp_path.stat().st_mode) == before
    published = tmp_path / "eval-abc"
    assert stat.S_IMODE(published.stat().st_mode) == 0o700
    assert stat.S_IMODE((published / "report.json").stat().st_mode) == 0o600
