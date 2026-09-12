"""Tests for RunManifest persistence."""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from vera.persistence.errors import PersistenceFault, StateVersionError
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
    assert caught.value.code == "checksum_mismatch"
    assert "保留原" in caught.value.advice


def test_manifest_rejects_missing_and_dangerous_fields(tmp_path: Path) -> None:
    store = RunManifestStore(tmp_path)
    store.save(RunManifest(run_id="run_1"))
    path = store.path_for("run_1")
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["run_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StateVersionError) as missing:
        store.load("run_1")
    assert missing.value.code == "missing_field"

    store.save(RunManifest(run_id="run_2"))
    extra_path = store.path_for("run_2")
    extra = json.loads(extra_path.read_text(encoding="utf-8"))
    extra["__proto__"] = {"x": 1}
    extra_path.write_text(json.dumps(extra), encoding="utf-8")
    with pytest.raises(StateVersionError) as unexpected:
        store.load("run_2")
    assert unexpected.value.code == "unexpected_field"


def test_manifest_enospc_does_not_clobber_or_succeed(tmp_path: Path) -> None:
    store = RunManifestStore(tmp_path)
    store.save(RunManifest(run_id="run_1"))
    original = store.path_for("run_1").read_bytes()

    def fail_fsync(_fd: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    failing = RunManifestStore(tmp_path, fsync=fail_fsync)
    with pytest.raises(PersistenceFault) as caught:
        failing.save(RunManifest(run_id="run_1"))
    assert caught.value.code == "no_space"
    assert store.path_for("run_1").read_bytes() == original
    assert not store.path_for("run_1").with_suffix(".json.tmp").exists()


def test_manifest_readonly_directory_does_not_clobber(tmp_path: Path) -> None:
    store = RunManifestStore(tmp_path)
    store.save(RunManifest(run_id="run_1"))
    path = store.path_for("run_1")
    original = path.read_bytes()

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError(errno.EROFS, "Read-only file system")

    failing = RunManifestStore(tmp_path, replace=fail_replace)
    with pytest.raises(PersistenceFault) as caught:
        failing.save(RunManifest(run_id="run_1"))
    assert caught.value.code == "read_only_filesystem"
    assert path.read_bytes() == original
    assert not path.with_suffix(".json.tmp").exists()
