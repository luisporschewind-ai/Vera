from pathlib import Path

from vera.workspace.apply import ApplyStatus, ChangeApplier
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


def test_apply_updates_and_creates_files(tmp_path: Path, state_dir: Path) -> None:
    (tmp_path / "old.txt").write_text("old\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    built = ChangeSetBuilder(paths).build(
        "run_1",
        "edit",
        [
            ChangeProposal(operation="update", path="old.txt", after_content="new\n"),
            ChangeProposal(operation="create", path="new.txt", after_content="created\n"),
        ],
        [],
    )
    store = CheckpointStore(state_dir, paths)
    manifest = store.create(built.change_set)
    result = ChangeApplier(paths, store).apply(built, manifest)
    assert result.status is ApplyStatus.APPLIED
    assert (tmp_path / "old.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "created\n"
