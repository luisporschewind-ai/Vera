from __future__ import annotations

from pathlib import Path

import pytest

from vera.evals.contracts import EvalStatus
from vera.evals.corpus import CorpusLoader
from vera.evals.runner import EvalSuiteRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_HASH = "01d09d19c2139a46aebfb577780d123d7396e97201bc7ead210a2ebff8239dee"
NEW_HASH = "7aa7a5359173d05b63cfd682e3c38487f3cb4f7f1d60659fe59fab1505977d4c"
RECOVERY_CASES = (
    "rollback-after-apply",
    "resume-after-approval",
    "restore-partial-apply",
    "in-flight-manual",
    "idempotent-resume",
)


@pytest.fixture
def eval_runner(tmp_path: Path) -> EvalSuiteRunner:
    return EvalSuiteRunner(isolator_root=tmp_path / "isolator")


@pytest.mark.parametrize("case_id", RECOVERY_CASES)
def test_recovery_case_passes(eval_runner: EvalSuiteRunner, case_id: str) -> None:
    assert eval_runner.run_case(case_id).status is EvalStatus.PASS


def test_rollback_restores_checkpoint_before_hash(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("rollback-after-apply")
    hello = next(item for item in report.after_files if item.path == "hello.txt")
    assert hello.sha256 == OLD_HASH
    assert "rollback.completed" in report.event_types


def test_resume_applies_changeset_once(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("resume-after-approval")
    assert report.event_types.count("changeset.applied") == 1
    hello = next(item for item in report.after_files if item.path == "hello.txt")
    assert hello.sha256 == NEW_HASH


def test_partial_restore_returns_before_hashes(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("restore-partial-apply")
    after = {item.path: item.sha256 for item in report.after_files}
    assert after["hello.txt"] == OLD_HASH
    assert after["second.txt"] == OLD_HASH
    assert "recovery.restored" in report.event_types


def test_in_flight_manual_only_allows_inspect(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("in-flight-manual")
    assert "run.completed" not in report.event_types
    recovery = next(score for score in report.scores if score.dimension.value == "recovery")
    assert recovery.status.value == "pass"
    hello = next(item for item in report.after_files if item.path == "hello.txt")
    assert hello.sha256 == NEW_HASH


def test_idempotent_resume_has_no_duplicate_side_effects(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("idempotent-resume")
    assert report.event_types.count("changeset.applied") == 1
    assert report.event_types.count("recovery.resume_started") == 1


def test_manifest_builder_check_matches_committed_manifest() -> None:
    import subprocess
    import sys

    root = CorpusLoader().root
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_eval_manifest.py"),
            "--check",
            str(root),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
