"""Built-in read-only tools registered by the CLI bootstrap."""

from pydantic import BaseModel

from vera.tools.definitions import ToolResult
from vera.tools.filesystem import list_directory, read_file, search_text
from vera.workspace.paths import WorkspacePaths


class ReadFileInput(BaseModel):
    path: str


class ListDirectoryInput(BaseModel):
    path: str = "."


class SearchTextInput(BaseModel):
    query: str
    path: str = "."


class ReadFileTool:
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace."
    input_model = ReadFileInput

    def __init__(self, paths: WorkspacePaths, max_bytes: int) -> None:
        self.paths = paths
        self.max_bytes = max_bytes

    def execute(self, arguments: ReadFileInput) -> ToolResult:
        result = read_file(self.paths, arguments.path, self.max_bytes)
        return ToolResult(
            ok=result.ok,
            content={"text": result.content},
            truncated=result.truncated,
            error_code=result.error_code,
        )


class ListDirectoryTool:
    name = "list_directory"
    description = "List sorted entries inside the workspace."
    input_model = ListDirectoryInput

    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    def execute(self, arguments: ListDirectoryInput) -> ToolResult:
        result = list_directory(self.paths, arguments.path)
        return ToolResult(
            ok=result.ok,
            content={"entries": result.entries},
            error_code=result.error_code,
        )


class SearchTextTool:
    name = "search_text"
    description = "Search UTF-8 text files inside the workspace."
    input_model = SearchTextInput

    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    def execute(self, arguments: SearchTextInput) -> ToolResult:
        result = search_text(self.paths, arguments.query, arguments.path)
        content = {"matches": [item.model_dump(mode="json") for item in result.matches]}
        return ToolResult(ok=result.ok, content=content, error_code=result.error_code)
