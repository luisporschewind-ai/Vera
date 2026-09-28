from pathlib import Path

from vera.tools.filesystem import find_files, list_directory, read_file, search_text
from vera.workspace.paths import WorkspacePaths


def test_read_file_marks_truncation(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("abcdef", encoding="utf-8")
    result = read_file(WorkspacePaths(tmp_path), "large.txt", max_bytes=4)
    assert result.content == "abcd"
    assert result.truncated is True


def test_list_and_search_are_sorted_and_ignore_generated_dirs(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.txt").write_text("needle\n", encoding="utf-8")
    assert list_directory(WorkspacePaths(tmp_path), ".").entries == ["a.txt", "b.txt", ".venv"]
    matches = search_text(WorkspacePaths(tmp_path), "needle")
    assert [(item.path, item.line) for item in matches.matches] == [("a.txt", 1), ("b.txt", 1)]


def test_read_file_rejects_binary(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\xff\x00")
    result = read_file(WorkspacePaths(tmp_path), "binary.bin", max_bytes=10)
    assert result.ok is False
    assert result.error_code == "binary_or_non_utf8"


def test_search_text_accepts_a_single_file(tmp_path: Path) -> None:
    (tmp_path / "project.pbxproj").write_text(
        "IPHONEOS_DEPLOYMENT_TARGET = 17.0;\n",
        encoding="utf-8",
    )
    (tmp_path / "other.txt").write_text(
        "IPHONEOS_DEPLOYMENT_TARGET = 16.0;\n",
        encoding="utf-8",
    )
    result = search_text(
        WorkspacePaths(tmp_path),
        "IPHONEOS_DEPLOYMENT_TARGET",
        "project.pbxproj",
    )
    assert result.ok is True
    assert [(item.path, item.line) for item in result.matches] == [("project.pbxproj", 1)]


def test_search_text_missing_path_is_not_found(tmp_path: Path) -> None:
    result = search_text(WorkspacePaths(tmp_path), "needle", "missing.txt")
    assert result.ok is False
    assert result.error_code == "not_found"


def test_find_rejects_patterns_that_escape_workspace(tmp_path: Path) -> None:
    (tmp_path / "inside.txt").write_text("inside", encoding="utf-8")
    result = find_files(WorkspacePaths(tmp_path), "../*")
    assert result.ok is False
    assert result.error_code == "workspace_boundary"


def test_search_text_skips_symlinks_to_external_files(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("unique-external-marker", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(outside)
    except OSError:
        return
    result = search_text(WorkspacePaths(tmp_path), "unique-external-marker")
    assert result.ok is True
    assert result.matches == []
