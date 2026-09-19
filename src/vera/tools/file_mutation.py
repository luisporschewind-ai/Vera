"""Canonical write/edit tools backed by the shared file mutation pipeline."""

from pathlib import Path

from pydantic import BaseModel, Field

from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.workspace.mutation import (
    FileMutationApplier,
    FileMutationPlanner,
    PlannedFileMutation,
)
from vera.workspace.paths import WorkspacePaths


class WriteInput(BaseModel):
    path: str
    content: str
    expected_before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class EditInput(BaseModel):
    path: str
    old_text: str
    new_text: str
    expected_before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class _FileMutationTool:
    def __init__(self, root: Path) -> None:
        self.paths = WorkspacePaths(root)
        self.planner = FileMutationPlanner(self.paths)

    def risk_facts(self, arguments: BaseModel) -> ToolRiskFacts:
        if not isinstance(arguments, (WriteInput, EditInput)):
            raise TypeError("invalid mutation input")
        path = arguments.path
        return ToolRiskFacts(
            normalized_paths=(path,),
            recoverable=True,
            facts_complete=True,
        )

    def plan_action(self, run_id: str, arguments: BaseModel) -> PlannedFileMutation:
        raise NotImplementedError

    def execute(self, _arguments: BaseModel) -> ToolResult:
        return ToolResult(ok=False, error_code="mutation_requires_executor")


class WriteTool(_FileMutationTool):
    name = "write"
    input_model = WriteInput
    definition = ToolDefinitionV2(
        name=name,
        description="Create or replace a UTF-8 workspace file.",
        input_schema=WriteInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_WRITE,),
        supports_cancellation=False,
        supports_recovery=True,
        max_output_bytes=16_384,
    )

    def __init__(self, root: Path, state_dir: Path | None = None) -> None:
        super().__init__(root)
        self.state_dir = state_dir
        self.applier: FileMutationApplier | None = None

    def bind_state(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.applier = FileMutationApplier(self.paths, state_dir)

    def plan_action(self, run_id: str, arguments: BaseModel) -> PlannedFileMutation:
        parsed = WriteInput.model_validate(arguments.model_dump())
        return self.planner.plan_write(
            run_id,
            parsed.path,
            parsed.content,
            expected_before_hash=parsed.expected_before_hash,
        )


class EditTool(_FileMutationTool):
    name = "edit"
    input_model = EditInput
    definition = ToolDefinitionV2(
        name=name,
        description="Apply one unique exact UTF-8 text replacement in a workspace file.",
        input_schema=EditInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_WRITE,),
        supports_cancellation=False,
        supports_recovery=True,
        max_output_bytes=16_384,
    )

    def __init__(self, root: Path, state_dir: Path | None = None) -> None:
        super().__init__(root)
        self.state_dir = state_dir
        self.applier: FileMutationApplier | None = None

    def bind_state(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.applier = FileMutationApplier(self.paths, state_dir)

    def plan_action(self, run_id: str, arguments: BaseModel) -> PlannedFileMutation:
        parsed = EditInput.model_validate(arguments.model_dump())
        return self.planner.plan_edit(
            run_id,
            parsed.path,
            parsed.old_text,
            parsed.new_text,
            expected_before_hash=parsed.expected_before_hash,
        )
