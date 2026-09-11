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
