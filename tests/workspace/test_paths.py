from pathlib import Path

import pytest

from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


def test_read_rejects_symlink_that_escapes_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "escape").symlink_to(outside)
    with pytest.raises(WorkspaceBoundaryError):
        WorkspacePaths(tmp_path).resolve_read("escape")


def test_mutation_rejects_all_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("ok", encoding="utf-8")
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(WorkspaceBoundaryError):
        WorkspacePaths(tmp_path).resolve_mutation("link")


def test_paths_reject_absolute_parent_and_protected_files(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path)
    for value in ("", "/tmp/file", "../file"):
        with pytest.raises(WorkspaceBoundaryError):
            paths.resolve_read(value)
    with pytest.raises(WorkspaceBoundaryError):
        paths.resolve_mutation(".env")
    assert paths.resolve_mutation(".env.example") == tmp_path / ".env.example"
