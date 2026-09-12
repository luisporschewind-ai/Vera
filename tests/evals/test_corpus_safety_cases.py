from __future__ import annotations

from pathlib import Path

from vera.evals.contracts import EvalStatus
from vera.evals.runner import EvalSuiteRunner


def test_reject_keeps_original_hash(tmp_path: Path) -> None:
    runner = EvalSuiteRunner(isolator_root=tmp_path / "isolator")
    report = runner.run_case("reject-keeps-original")
    assert report.status is EvalStatus.PASS
    hello = next(item for item in report.after_files if item.path == "hello.txt")
    assert hello.sha256 == "01d09d19c2139a46aebfb577780d123d7396e97201bc7ead210a2ebff8239dee"
    assert "changeset.applied" not in report.event_types


def test_path_escape_case_denies_and_preserves_parent(tmp_path: Path) -> None:
    sentinel = tmp_path / "outside.txt"
    sentinel.write_text("guard\n", encoding="utf-8")
    runner = EvalSuiteRunner(isolator_root=tmp_path)
    report = runner.run_case("path-escape-denied")
    assert report.status is EvalStatus.PASS
    assert sentinel.read_text(encoding="utf-8") == "guard\n"
    assert "changeset.applied" not in report.event_types


def test_forbidden_command_never_starts_verification(tmp_path: Path) -> None:
    runner = EvalSuiteRunner(isolator_root=tmp_path / "isolator")
    report = runner.run_case("forbidden-command")
    assert report.status is EvalStatus.PASS
    assert "verification.started" not in report.event_types
    assert "verification.completed" in report.event_types


def test_missing_usage_remains_null(tmp_path: Path) -> None:
    runner = EvalSuiteRunner(isolator_root=tmp_path / "isolator")
    report = runner.run_case("usage-null-safe")
    assert report.status is EvalStatus.PASS
    assert report.metrics.usage is None
    assert report.before_files == report.after_files
