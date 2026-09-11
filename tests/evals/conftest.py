from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vera.evals.corpus import CorpusLoader
from vera.evals.isolation import FixtureIsolator

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "evals" / "valid"


@pytest.fixture
def loaded_and_isolated(tmp_path: Path):
    corpus = tmp_path / "corpus"
    shutil.copytree(FIXTURE_ROOT, corpus)
    loaded = CorpusLoader(corpus).load("plain-answer")
    isolated = FixtureIsolator(tmp_path / "tmp").prepare(loaded)
    return loaded, isolated
