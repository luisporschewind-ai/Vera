"""Built-in read-only tools registered by the CLI bootstrap."""

from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.filesystem import find_files, list_directory, read_file, search_text
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths


class ReadFileInput(BaseModel):
    path: str


class ListDirectoryInput(BaseModel):
    path: str = "."


class SearchTextInput(BaseModel):
    query: str
    path: str = "."


class FindInput(BaseModel):
    pattern: str = "*"
    path: str = "."


class _WorkspaceReadTool:
    paths: WorkspacePaths

    def risk_facts(self, arguments: BaseModel) -> ToolRiskFacts:
        raw_path = str(getattr(arguments, "path", "."))
        try:
            fact = self.paths.inspect_read(raw_path)
        except WorkspaceBoundaryError as exc:
            return ToolRiskFacts(
                normalized_paths=(raw_path,),
                outside_workspace=exc.code in {"not_workspace_relative", "path_escapes_workspace"},
                protected_target=exc.code == "protected_path",
                facts_complete=True,
            )
        return ToolRiskFacts(
            normalized_paths=(fact.relative_path,),
            protected_target=self.paths.protected.is_protected(Path(fact.relative_path)),
            facts_complete=True,
        )


class ReadTool(_WorkspaceReadTool):
    name = "read"
    description = "Read a UTF-8 text file inside the workspace."
    input_model = ReadFileInput

    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=ReadFileInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

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


class LsTool(_WorkspaceReadTool):
    name = "ls"
    description = "List sorted entries inside the workspace."
    input_model = ListDirectoryInput

    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=ListDirectoryInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    def execute(self, arguments: ListDirectoryInput) -> ToolResult:
        result = list_directory(self.paths, arguments.path)
        return ToolResult(
            ok=result.ok,
            content={"entries": result.entries},
            error_code=result.error_code,
        )


class GrepTool(_WorkspaceReadTool):
    name = "grep"
    description = "Search UTF-8 text inside a workspace directory or a single file."
    input_model = SearchTextInput

    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=SearchTextInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    def execute(self, arguments: SearchTextInput) -> ToolResult:
        result = search_text(self.paths, arguments.query, arguments.path)
        content = {"matches": [item.model_dump(mode="json") for item in result.matches]}
        return ToolResult(ok=result.ok, content=content, error_code=result.error_code)


class FindTool(_WorkspaceReadTool):
    name = "find"
    description = "Find regular files inside the workspace using a glob pattern."
    input_model = FindInput
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=FindInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    def risk_facts(self, arguments: BaseModel) -> ToolRiskFacts:
        facts = super().risk_facts(arguments)
        pattern = PurePosixPath(str(getattr(arguments, "pattern", "*")).replace("\\", "/"))
        if pattern.is_absolute() or ".." in pattern.parts:
            return facts.model_copy(update={"outside_workspace": True})
        return facts

    def execute(self, arguments: FindInput) -> ToolResult:
        result = find_files(self.paths, arguments.pattern, arguments.path)
        return ToolResult(
            ok=result.ok,
            content={"paths": result.paths},
            error_code=result.error_code,
        )


class ReadFileTool(ReadTool):
    """Historical decoder/fixture name; never registered by a new bootstrap."""

    name = "read_file"
    definition = ToolDefinitionV2(
        name=name,
        description=ReadTool.description,
        input_schema=ReadFileInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )


class ListDirectoryTool(LsTool):
    """Historical decoder/fixture name; never registered by a new bootstrap."""

    name = "list_directory"
    definition = ToolDefinitionV2(
        name=name,
        description=LsTool.description,
        input_schema=ListDirectoryInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )


class SearchTextTool(GrepTool):
    """Historical decoder/fixture name; never registered by a new bootstrap."""

    name = "search_text"
    definition = ToolDefinitionV2(
        name=name,
        description=GrepTool.description,
        input_schema=SearchTextInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )
