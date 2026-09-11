from __future__ import annotations

import hashlib
import shutil
import stat
from pathlib import Path

import pytest

from vera.evals.corpus import CorpusLoader
from vera.evals.isolation import FixtureIsolator, IsolationError

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "evals" / "valid"


@pytest.fixture
def valid_loaded_case(tmp_path: Path):
    corpus = tmp_path / "corpus"
    shutil.copytree(FIXTURE_ROOT, corpus)
    return CorpusLoader(corpus).load("plain-answer")


def test_isolator_never_runs_in_source_workspace(valid_loaded_case, tmp_path: Path) -> None:
    isolated = FixtureIsolator(tmp_path / "tmp").prepare(valid_loaded_case)
    assert isolated.workspace != valid_loaded_case.source_root / "workspace"
    assert (isolated.workspace / "README.md").read_bytes() == b"fixture\n"
    assert isolated.state_dir.parent == isolated.workspace.parent
    assert isolated.staging_dir.parent == isolated.workspace.parent
    assert isolated.workspace.parent.name.startswith("vera-eval-")
    roots = (
        isolated.workspace.parent,
        isolated.workspace,
        isolated.state_dir,
        isolated.staging_dir,
    )
    for path in roots:
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    current = CorpusLoader(valid_loaded_case.corpus_root).validate().manifest_hash
    isolated.verify_source_unchanged(current)


def test_isolator_detects_source_mutation(valid_loaded_case, tmp_path: Path) -> None:
    isolated = FixtureIsolator(tmp_path / "tmp").prepare(valid_loaded_case)
    (valid_loaded_case.source_root / "case.json").write_text("{}\n", encoding="utf-8")
    mutated = hashlib.sha256(b"changed").hexdigest()
    with pytest.raises(IsolationError, match="source_changed"):
        isolated.verify_source_unchanged(mutated)


def test_isolator_rejects_symlink_in_source_workspace(valid_loaded_case, tmp_path: Path) -> None:
    link = valid_loaded_case.workspace_root / "alias.md"
    link.symlink_to(valid_loaded_case.workspace_root / "README.md")
    with pytest.raises(IsolationError, match="special_file"):
        FixtureIsolator(tmp_path / "tmp").prepare(valid_loaded_case)


def test_isolator_cleanup_is_idempotent(valid_loaded_case, tmp_path: Path) -> None:
    isolated = FixtureIsolator(tmp_path / "tmp").prepare(valid_loaded_case)
    case_root = isolated.workspace.parent
    isolated.cleanup()
    assert not case_root.exists()
    isolated.cleanup()


def test_isolator_cleans_partial_copy_on_failure(
    valid_loaded_case, tmp_path: Path, monkeypatch
) -> None:
    original = FixtureIsolator._copy_file

    def boom(self, source: Path, destination: Path) -> None:
        original(self, source, destination)
        raise IsolationError("copy_interrupted", source, "injected failure")

    monkeypatch.setattr(FixtureIsolator, "_copy_file", boom)
    isolator = FixtureIsolator(tmp_path / "tmp")
    with pytest.raises(IsolationError, match="copy_interrupted"):
        isolator.prepare(valid_loaded_case)
    remaining = list((tmp_path / "tmp").glob("vera-eval-*"))
    assert remaining == []


def test_isolator_rejects_existing_destination(
    valid_loaded_case, tmp_path: Path, monkeypatch
) -> None:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    existing = temp_root / "vera-eval-collision"
    existing.mkdir()

    def collide(prefix: str, dir: str | None = None) -> str:
        return str(existing)

    monkeypatch.setattr("vera.evals.isolation.tempfile.mkdtemp", collide)
    with pytest.raises(IsolationError, match="destination_exists"):
        FixtureIsolator(temp_root).prepare(valid_loaded_case)
    assert existing.is_dir()
