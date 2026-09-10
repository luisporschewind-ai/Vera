from pathlib import Path

from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder, sha256_bytes
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


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
