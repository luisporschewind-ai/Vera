"""Canonical, structured read-only Git tools."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from vera.contracts import ContractModel
from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.git.models import (
    GitDiffRequest,
    GitLogRequest,
    GitShowRequest,
)
from vera.git.service import GitService, GitServiceError
from vera.tools.definitions import ToolDefinitionV2, ToolResult


class GitStatusInput(ContractModel):
    """No arguments: inspect the configured workspace repository."""


class _GitReadTool:
    name: str
    input_model: type[ContractModel]
    service_method: str
    service: GitService | None

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.service = None

    def _service(self) -> GitService:
        if self.service is None:
            self.service = GitService(self.workspace)
        return self.service

    def risk_facts(self, arguments: ContractModel) -> ToolRiskFacts:
        raw_paths = tuple(str(path) for path in getattr(arguments, "paths", ())) or (".",)
        outside = any(
            not raw
            or PurePosixPath(raw.replace("\\", "/")).is_absolute()
            or ".." in PurePosixPath(raw.replace("\\", "/")).parts
            for raw in raw_paths
        )
        return ToolRiskFacts(
            normalized_paths=raw_paths,
            argv=("git", self.name.removeprefix("git_").replace("branch_list", "branch")),
            cwd=".",
            outside_workspace=outside,
            facts_complete=True,
        )

    def _result(self, content: Any) -> ToolResult:
        return ToolResult(ok=True, content=content)

    @staticmethod
    def _error(exc: GitServiceError) -> ToolResult:
        return ToolResult(ok=False, error_code=exc.code)


class GitStatusTool(_GitReadTool):
    name = "git_status"
    description = "Read structured repository status for the current workspace."
    input_model = GitStatusInput
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=GitStatusInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ, ToolEffect.PROCESS_EXECUTE),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def execute(self, arguments: GitStatusInput) -> ToolResult:
        try:
            return self._result(self._service().status().model_dump(mode="json"))
        except GitServiceError as exc:
            return self._error(exc)


class GitDiffTool(_GitReadTool):
    name = "git_diff"
    description = "Read a bounded structured diff for the current workspace repository."
    input_model = GitDiffRequest
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=GitDiffRequest.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ, ToolEffect.PROCESS_EXECUTE),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def execute(self, arguments: GitDiffRequest) -> ToolResult:
        try:
            return self._result(self._service().diff(arguments).model_dump(mode="json"))
        except GitServiceError as exc:
            return self._error(exc)


class GitLogTool(_GitReadTool):
    name = "git_log"
    description = "Read bounded structured commit summaries from the local repository."
    input_model = GitLogRequest
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=GitLogRequest.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ, ToolEffect.PROCESS_EXECUTE),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def execute(self, arguments: GitLogRequest) -> ToolResult:
        try:
            commits = self._service().log(arguments)
            return self._result([commit.model_dump(mode="json") for commit in commits])
        except GitServiceError as exc:
            return self._error(exc)


class GitShowTool(_GitReadTool):
    name = "git_show"
    description = "Read one structured local commit summary and bounded diff."
    input_model = GitShowRequest
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=GitShowRequest.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ, ToolEffect.PROCESS_EXECUTE),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def execute(self, arguments: GitShowRequest) -> ToolResult:
        try:
            return self._result(self._service().show(arguments).model_dump(mode="json"))
        except GitServiceError as exc:
            return self._error(exc)


class GitBranchListTool(_GitReadTool):
    name = "git_branch_list"
    description = "Read structured local branch and tracking information."
    input_model = GitStatusInput
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=GitStatusInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ, ToolEffect.PROCESS_EXECUTE),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100_000,
    )

    def execute(self, arguments: GitStatusInput) -> ToolResult:
        try:
            branches = self._service().branches()
            return self._result([branch.model_dump(mode="json") for branch in branches])
        except GitServiceError as exc:
            return self._error(exc)
