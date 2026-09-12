from __future__ import annotations

from vera.evals.corpus import CorpusLoader
from vera.evals.determinism import CanonicalComparator
from vera.evals.runner import EvalSuiteRunner

ALL_CASE_IDS = tuple(case.case_id for case in CorpusLoader().list_cases())


def test_offline_suite_is_repeatable(eval_runner: EvalSuiteRunner) -> None:
    first = eval_runner.run_suite(ALL_CASE_IDS)
    second = eval_runner.run_suite(ALL_CASE_IDS)
    comparison = CanonicalComparator().compare(first, second)
    assert comparison.equal, comparison.differences
    assert len(first.cases) == 14
    assert len(second.cases) == 14
