import os
from pathlib import Path

import pytest

from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder, sha256_bytes
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


def test_checkpoint_records_original_bytes_and_absent_files(
    tmp_path: Path, state_dir: Path
) -> None:
    (tmp_path / "old.txt").write_bytes(b"old\n")
    built = ChangeSetBuilder(WorkspacePaths(tmp_path)).build(
        "run_1",
        "edit",
        [
            ChangeProposal(operation="update", path="old.txt", after_content="new\n"),
            ChangeProposal(operation="create", path="new.txt", after_content="created\n"),
        ],
        [],
    )
    store = CheckpointStore(state_dir, WorkspacePaths(tmp_path))
    manifest = store.create(built.change_set)
    assert manifest.before["old.txt"].content_hash == sha256_bytes(b"old\n")
    assert manifest.before["new.txt"].existed is False
    assert (state_dir / "runs" / "run_1" / "checkpoint" / "manifest.json").exists()
    assert store.load_for_run("run_1") == manifest


def test_checkpoint_rejects_changed_baseline(tmp_path: Path, state_dir: Path) -> None:
    (tmp_path / "old.txt").write_bytes(b"old\n")
    built = ChangeSetBuilder(WorkspacePaths(tmp_path)).build(
        "run_1",
        "edit",
        [ChangeProposal(operation="update", path="old.txt", after_content="new\n")],
        [],
    )
    (tmp_path / "old.txt").write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="before hash changed"):
        CheckpointStore(state_dir, WorkspacePaths(tmp_path)).create(built.change_set)


def test_checkpoint_rejects_non_regular_file(tmp_path: Path, state_dir: Path) -> None:
    os.mkfifo(tmp_path / "named.pipe")
    paths = WorkspacePaths(tmp_path)
    with pytest.raises(WorkspaceBoundaryError) as caught:
        paths.inspect_mutation("named.pipe")
    assert caught.value.code == "special_file"
    with pytest.raises(WorkspaceBoundaryError):
        CheckpointStore(state_dir, paths).create(
            ChangeSetBuilder(paths)
            .build(
                "run_1",
                "edit",
                [ChangeProposal(operation="update", path="named.pipe", after_content="x\n")],
                [],
            )
            .change_set
        )
