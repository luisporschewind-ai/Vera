from __future__ import annotations

import ast
from pathlib import Path

from vera.evals.contracts import EvalStatus, EvalTag
from vera.evals.corpus import CorpusLoader
from vera.evals.runner import EvalSuiteRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_PACKAGE = REPO_ROOT / "src" / "vera" / "evals"


def imported_modules_under(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def test_phase4_offline_suite_passes_all_frozen_cases(tmp_path: Path) -> None:
    corpus_loader = CorpusLoader()
    eval_runner = EvalSuiteRunner(isolator_root=tmp_path / "isolator")
    report = eval_runner.run_suite(tuple(case.case_id for case in corpus_loader.list_cases()))
    assert report.status is EvalStatus.PASS
    assert len(report.cases) == 14
    assert {tag for case in corpus_loader.list_cases() for tag in case.tags} == {
        EvalTag.CORRECTNESS,
        EvalTag.SAFETY,
        EvalTag.RECOVERY,
        EvalTag.CONVERSATION,
    }
    before = corpus_loader.validate().manifest_hash
    after = CorpusLoader().validate().manifest_hash
    assert before == after


def test_eval_package_has_no_human_presenter_dependency() -> None:
    imported = imported_modules_under(EVALS_PACKAGE)
    assert "vera.cli_presenter" not in imported
    assert not any(name.startswith("vera.terminal") for name in imported)
