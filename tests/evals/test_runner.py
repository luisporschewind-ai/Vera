import stat
from pathlib import Path

from vera.contracts.compatibility import current_compatibility_manifest
from vera.evals.contracts import EvalStatus
from vera.evals.runner import EvalSuiteRunner


def test_suite_continues_after_failed_case() -> None:
    def fake_run(case_id: str, output_root=None):
        del output_root
        from vera.evals.contracts import DimensionStatus, EvalReport, EvalScore

        status = {
            "pass-case": EvalStatus.PASS,
            "second-pass": EvalStatus.PASS,
            "timeout-case": EvalStatus.TIMEOUT,
        }[case_id]
        return EvalReport(
            evaluation_id=f"eval-{case_id}",
            case_id=case_id,
            status=status,
            scores=(EvalScore(dimension="correctness", status=DimensionStatus.PASS),),
        )

    runner = EvalSuiteRunner(case_runner=fake_run)
    report = runner.run_suite(("pass-case", "timeout-case", "second-pass"))
    assert [item.case_id for item in report.cases] == [
        "pass-case",
        "second-pass",
        "timeout-case",
    ]
    assert report.status is EvalStatus.FAIL


def test_suite_report_is_atomic_and_preserves_parent_mode(tmp_path: Path) -> None:
    def fake_run(case_id: str, output_root=None):
        del case_id, output_root
        from vera.evals.contracts import DimensionStatus, EvalReport, EvalScore

        return EvalReport(
            evaluation_id="eval-one",
            case_id="pass-case",
            status=EvalStatus.PASS,
            scores=(EvalScore(dimension="correctness", status=DimensionStatus.PASS),),
        )

    tmp_path.chmod(0o755)
    before = stat.S_IMODE(tmp_path.stat().st_mode)
    runner = EvalSuiteRunner(case_runner=fake_run)
    runner.run_suite(("pass-case",), output_root=tmp_path)
    target = tmp_path / "suite-report.json"
    assert target.is_file()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == before
    assert not any(
        path.name.startswith(".") for path in tmp_path.iterdir() if path.name != "eval-one"
    )


def test_eval_runner_is_a_core_client_not_a_human_protocol() -> None:
    manifest = current_compatibility_manifest()
    assert "start_run" in {item.name for item in manifest.commands}
    assert "event" in manifest.runtime_output
