from pathlib import Path

from vera.contracts.verification import VerificationCommand
from vera.workspace.changeset import ChangeProposal, ChangeSetBuilder
from vera.workspace.paths import WorkspacePaths


def test_changeset_hash_covers_files_and_verification(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    builder = ChangeSetBuilder(WorkspacePaths(tmp_path))
    pytest_command = VerificationCommand(argv=("python", "-m", "pytest"))
    ruff_command = VerificationCommand(argv=("ruff", "check", "."))
    first = builder.build(
        "run_1",
        "更新问候",
        [ChangeProposal(operation="update", path="hello.txt", after_content="new\n")],
        [pytest_command],
    )
    second = builder.build(
        "run_1",
        "更新问候",
        [ChangeProposal(operation="update", path="hello.txt", after_content="new\n")],
        [ruff_command],
    )
    assert first.change_set.files[0].unified_diff.startswith("--- a/hello.txt")
    assert first.change_set.content_hash != second.change_set.content_hash


def test_changeset_supports_create_delete_and_stable_order(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("remove\n", encoding="utf-8")
    builder = ChangeSetBuilder(WorkspacePaths(tmp_path))
    proposals = [
        ChangeProposal(operation="create", path="b.txt", after_content="b\n"),
        ChangeProposal(operation="delete", path="z.txt"),
        ChangeProposal(operation="create", path="a.txt", after_content="a\n"),
    ]
    first = builder.build("run_1", "files", proposals, [])
    second = builder.build("run_1", "files", list(reversed(proposals)), [])
    assert [item.path for item in first.change_set.files] == ["a.txt", "b.txt", "z.txt"]
    assert first.change_set.content_hash == second.change_set.content_hash
    assert first.intended_bytes["a.txt"] == b"a\n"
