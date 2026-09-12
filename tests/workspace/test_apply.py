from pathlib import Path

from vera.workspace.apply import ApplyStatus, ChangeApplier
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.checkpoint import CheckpointStore
from vera.workspace.paths import WorkspacePaths


class RecordingWriter:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
        del content, mode
        self.writes.append(f"replace:{path.name}")
        raise AssertionError("writer must not be called after fact mismatch")

    def delete(self, path: Path) -> None:
        self.writes.append(f"delete:{path.name}")
        raise AssertionError("writer must not be called after fact mismatch")


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


def test_apply_rejects_inode_replacement_with_zero_writes(tmp_path: Path, state_dir: Path) -> None:
    (tmp_path / "old.txt").write_text("old\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    built = ChangeSetBuilder(paths).build(
        "run_1",
        "edit",
        [ChangeProposal(operation="update", path="old.txt", after_content="new\n")],
        [],
    )
    store = CheckpointStore(state_dir, paths)
    manifest = store.create(built.change_set)
    (tmp_path / "old.txt").unlink()
    (tmp_path / "old.txt").write_text("old\n", encoding="utf-8")
    writer = RecordingWriter()
    result = ChangeApplier(paths, store, writer=writer).apply(built, manifest)
    assert result.status is ApplyStatus.REJECTED
    assert writer.writes == []
    assert (tmp_path / "old.txt").read_text(encoding="utf-8") == "old\n"


def test_apply_rejects_symlink_swap_with_zero_writes(tmp_path: Path, state_dir: Path) -> None:
    (tmp_path / "old.txt").write_text("old\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    built = ChangeSetBuilder(paths).build(
        "run_1",
        "edit",
        [ChangeProposal(operation="update", path="old.txt", after_content="new\n")],
        [],
    )
    store = CheckpointStore(state_dir, paths)
    manifest = store.create(built.change_set)
    (tmp_path / "old.txt").unlink()
    (tmp_path / "other.txt").write_text("other\n", encoding="utf-8")
    (tmp_path / "old.txt").symlink_to(tmp_path / "other.txt")
    writer = RecordingWriter()
    result = ChangeApplier(paths, store, writer=writer).apply(built, manifest)
    assert result.status is ApplyStatus.REJECTED
    assert writer.writes == []
    assert (tmp_path / "other.txt").read_text(encoding="utf-8") == "other\n"


def test_multifile_fact_change_fails_before_first_write(tmp_path: Path, state_dir: Path) -> None:
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    built = ChangeSetBuilder(paths).build(
        "run_1",
        "edit",
        [
            ChangeProposal(operation="update", path="a.txt", after_content="A\n"),
            ChangeProposal(operation="update", path="b.txt", after_content="B\n"),
        ],
        [],
    )
    store = CheckpointStore(state_dir, paths)
    manifest = store.create(built.change_set)
    (tmp_path / "b.txt").write_text("changed\n", encoding="utf-8")
    writer = RecordingWriter()
    result = ChangeApplier(paths, store, writer=writer).apply(built, manifest)
    assert result.status is ApplyStatus.REJECTED
    assert writer.writes == []
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a\n"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "changed\n"


def test_apply_enospc_does_not_complete_and_reports_next_step(
    tmp_path: Path, state_dir: Path
) -> None:
    import errno

    (tmp_path / "old.txt").write_text("old\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)
    built = ChangeSetBuilder(paths).build(
        "run_1",
        "edit",
        [ChangeProposal(operation="update", path="old.txt", after_content="new\n")],
        [],
    )
    store = CheckpointStore(state_dir, paths)
    manifest = store.create(built.change_set)

    class EnospcWriter:
        def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
            del path, content, mode
            raise OSError(errno.ENOSPC, "No space left on device")

        def delete(self, path: Path) -> None:
            del path
            raise OSError(errno.ENOSPC, "No space left on device")

    result = ChangeApplier(paths, store, writer=EnospcWriter()).apply(built, manifest)
    assert result.status is ApplyStatus.RECOVERY_REQUIRED
    assert result.written is False
    assert result.rollbackable is False
    assert result.next_step == "restore"
    assert result.error_code == "no_space"
    assert (tmp_path / "old.txt").read_text(encoding="utf-8") == "old\n"
