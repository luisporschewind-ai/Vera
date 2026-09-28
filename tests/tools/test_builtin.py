from pathlib import Path

from vera.tools.builtin import (
    FindInput,
    FindTool,
    GrepTool,
    ListDirectoryInput,
    LsTool,
    ReadFileInput,
    ReadTool,
    SearchTextInput,
)
from vera.workspace.paths import WorkspacePaths


def test_read_file_tool_returns_model_context(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    result = ReadTool(WorkspacePaths(tmp_path), 100).execute(ReadFileInput(path="hello.txt"))
    assert result.ok is True
    assert result.content == {"text": "hello\n"}


def test_canonical_read_tools_expose_stable_names_and_relative_results(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "a.txt").write_text("needle\n", encoding="utf-8")
    paths = WorkspacePaths(tmp_path)

    assert ReadTool.name == "read"
    assert GrepTool.name == "grep"
    assert FindTool.name == "find"
    assert LsTool.name == "ls"
    grep = GrepTool(paths).execute(SearchTextInput(query="needle"))
    assert grep.content is not None
    assert grep.content["matches"][0]["path"] == "dir/a.txt"
    assert FindTool(paths).execute(FindInput(pattern="*.txt")).content == {"paths": ["dir/a.txt"]}
    assert LsTool(paths).execute(ListDirectoryInput(path="dir")).content == {"entries": ["a.txt"]}
