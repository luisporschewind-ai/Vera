"""Tests for RunManifest persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from vera.persistence.errors import StateVersionError
from vera.persistence.journal import EventJournal
from vera.persistence.run_manifest import RunManifest, RunManifestStore
from vera.redaction import Redactor


def test_manifest_is_written_before_first_event(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path, "run_1", Redactor([]))
    journal.append("run.started", {"goal": "demo"})
    manifest = RunManifestStore(tmp_path).load("run_1")
    assert manifest.journal_format_version == 1
    assert manifest.run_id == "run_1"


def test_manifest_rejects_future_version(tmp_path: Path) -> None:
    store = RunManifestStore(tmp_path)
    store.save(RunManifest(run_id="run_1"))
    path = store.path_for("run_1")
    path.write_text('{"manifest_version":99,"journal_format_version":1,"run_id":"run_1"}')
    with pytest.raises(StateVersionError) as caught:
        store.load("run_1")
    assert caught.value.code == "unsupported_version"
    assert caught.value.version == 99


def test_manifest_run_id_mismatch(tmp_path: Path) -> None:
    store = RunManifestStore(tmp_path)
    directory = tmp_path / "runs" / "run_1"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        '{"manifest_version":1,"journal_format_version":1,"run_id":"other","created_at":"2026-09-11T00:00:00Z"}',
        encoding="utf-8",
    )
    with pytest.raises(StateVersionError) as caught:
        store.load("run_1")
    assert caught.value.code == "manifest_run_id_mismatch"
