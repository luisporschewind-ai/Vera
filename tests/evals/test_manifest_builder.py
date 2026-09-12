from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from vera.evals.corpus import CorpusLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "scripts" / "build_eval_manifest.py"


def _run_builder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_manifest_builder_write_then_check(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    case = root / "plain-answer"
    (case / "workspace").mkdir(parents=True)
    (case / "case.json").write_text(
        '{"schema_version":1,"case_id":"plain-answer","title":"t","goal":"g",'
        '"tags":["conversation"],"model":"fake","timeout_seconds":15,'
        '"scenario":"standard"}',
        encoding="utf-8",
    )
    (case / "script.json").write_text(
        '{"schema_version":1,"turns":[],"text_deltas":[],"approvals":[]}',
        encoding="utf-8",
    )
    (case / "expect.json").write_text('{"schema_version":1}', encoding="utf-8")
    (case / "workspace" / "README.md").write_text("fixture\n", encoding="utf-8")
    assert _run_builder("--write", str(root)).returncode == 0
    assert _run_builder("--check", str(root)).returncode == 0
    (case / "workspace" / "README.md").write_text("changed\n", encoding="utf-8")
    assert _run_builder("--check", str(root)).returncode == 1


def test_bundled_manifest_matches_builder() -> None:
    root = CorpusLoader().root
    assert _run_builder("--check", str(root)).returncode == 0
