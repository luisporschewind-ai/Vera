from pathlib import Path

from vera.tools.builtin import ReadFileInput, ReadFileTool
from vera.workspace.paths import WorkspacePaths


def test_read_file_tool_returns_model_context(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    result = ReadFileTool(WorkspacePaths(tmp_path), 100).execute(ReadFileInput(path="hello.txt"))
    assert result.ok is True
    assert result.content == {"text": "hello\n"}
