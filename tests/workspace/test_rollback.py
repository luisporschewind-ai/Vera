from pathlib import Path

from vera.workspace.apply import ChangeApplier, RollbackStatus
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


def _applied(tmp_path: Path, state_dir: Path) -> tuple[ChangeApplier, object]:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    built = ChangeSetBuilder(paths).build(
        "run_1",
        "edit",
        [ChangeProposal(operation="update", path="hello.txt", after_content="new\n")],
        [],
    )
    store = CheckpointStore(state_dir, paths)
    manifest = store.create(built.change_set)
    applier = ChangeApplier(paths, store)
    applier.apply(built, manifest)
    return applier, manifest


def test_rollback_refuses_to_overwrite_user_edit(tmp_path: Path, state_dir: Path) -> None:
    applier, manifest = _applied(tmp_path, state_dir)
    (tmp_path / "hello.txt").write_text("user edit\n", encoding="utf-8")
    result = applier.rollback(manifest)
    assert result.status is RollbackStatus.CONFLICTED
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "user edit\n"


def test_rollback_restores_original_bytes(tmp_path: Path, state_dir: Path) -> None:
    applier, manifest = _applied(tmp_path, state_dir)
    result = applier.rollback(manifest)
    assert result.status is RollbackStatus.ROLLED_BACK
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"
