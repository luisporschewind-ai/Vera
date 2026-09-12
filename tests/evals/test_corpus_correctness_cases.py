from __future__ import annotations

from pathlib import Path

import pytest

from vera.evals.contracts import EvalStatus
from vera.evals.corpus import CorpusLoader
from vera.evals.runner import EvalSuiteRunner

CASES = (
    "create-file",
    "update-file",
    "multi-file-edit",
    "plain-answer",
    "verification-passes",
)

HASHES = {
    "create-file": {
        "hello.txt": "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
    },
    "update-file": {
        "hello.txt": "7aa7a5359173d05b63cfd682e3c38487f3cb4f7f1d60659fe59fab1505977d4c"
    },
    "multi-file-edit": {
        "first.txt": "bd52020371c038c4ad38a8d2df05dfa1a220d40fbe1ae83b63d6010cb527e531",
        "second.txt": "465a43c7b7b79945ec5bc4dd80b20230ea1a992bd6401fe2ed5f736d67799e0c",
    },
}


@pytest.fixture
def corpus_loader() -> CorpusLoader:
    return CorpusLoader()


@pytest.fixture
def eval_runner(tmp_path: Path) -> EvalSuiteRunner:
    return EvalSuiteRunner(isolator_root=tmp_path / "isolator")


@pytest.mark.parametrize("case_id", CASES)
def test_correctness_case_passes_and_source_is_unchanged(
    eval_runner: EvalSuiteRunner, corpus_loader: CorpusLoader, case_id: str
) -> None:
    before = corpus_loader.validate().manifest_hash
    report = eval_runner.run_case(case_id)
    assert report.status is EvalStatus.PASS
    assert corpus_loader.validate().manifest_hash == before


def test_create_update_and_multi_file_hashes(eval_runner: EvalSuiteRunner) -> None:
    for case_id, expected in HASHES.items():
        report = eval_runner.run_case(case_id)
        after = {item.path: item.sha256 for item in report.after_files}
        for path, digest in expected.items():
            assert after[path] == digest


def test_plain_answer_has_no_file_changes(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("plain-answer")
    assert report.before_files == report.after_files
    assert "assistant.message" in report.event_types


def test_verification_passes_uses_eval_python(eval_runner: EvalSuiteRunner) -> None:
    report = eval_runner.run_case("verification-passes")
    assert "verification.completed" in report.event_types
    assert report.event_types[-1] == "run.completed"
