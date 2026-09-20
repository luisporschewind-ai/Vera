"""Canonical, structured read-only Git tools."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from vera.contracts import ContractModel
from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.git.branches import GitBrancher, GitBranchError, GitBranchPlan, GitBranchPlanBuilder
from vera.git.commit import GitCommitter, GitCommitTransactionError
from vera.git.commit_plan import GitCommitPlan, GitCommitPlanBuilder, GitCommitPlanError
from vera.git.hooks import GitHookInspector
from vera.git.models import (
    GitDiffRequest,
    GitLogRequest,
    GitShowRequest,
)
from vera.git.service import GitService, GitServiceError
from vera.tools.definitions import ToolDefinitionV2, ToolResult


class GitStatusInput(ContractModel):
    """No arguments: inspect the configured workspace repository."""


class GitCommitInput(ContractModel):
    paths: tuple[str, ...]
    message: str
    action_ids: tuple[str, ...]
    verification_status: Literal["passed", "failed"] = "passed"


class GitBranchInput(ContractModel):
    branch_name: str


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


class GitCommitTool:
    name = "git_commit"
    description = "Commit only the exact verified paths from the current Run."
    input_model = GitCommitInput
    definition = ToolDefinitionV2(
        name=name,
        description=description,
        input_schema=GitCommitInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE),
        supports_cancellation=False,
        supports_recovery=True,
        max_output_bytes=100_000,
    )

    def __init__(self, workspace: Path, *, environment: Mapping[str, str] | None = None) -> None:
        self.workspace = Path(workspace)
        self.environment = dict(environment) if environment is not None else os.environ.copy()
        self.service: GitService | None = None
        self.state_dir: Path | None = None
        self._workspace_identity: str | None = None
        self._policy_hash: str | None = None
        self._workspace_trusted = False

    def bind_state(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)

    def bind_policy(self, workspace_identity: str, policy_hash: str, trusted: bool = False) -> None:
        self._workspace_identity = workspace_identity
        self._policy_hash = policy_hash
        self._workspace_trusted = trusted

    def _service(self) -> GitService:
        if self.service is None:
            self.service = GitService(self.workspace, environment=self.environment)
        return self.service

    def risk_facts(self, arguments: GitCommitInput) -> ToolRiskFacts:
        outside = any(
            not path
            or PurePosixPath(path.replace("\\", "/")).is_absolute()
            or ".." in PurePosixPath(path.replace("\\", "/")).parts
            for path in arguments.paths
        )
        try:
            hook_facts = GitHookInspector(self._service()).inspect()
        except GitServiceError:
            return ToolRiskFacts(
                normalized_paths=arguments.paths,
                argv=("git", "commit"),
                cwd=".",
                recoverable=True,
                outside_workspace=outside,
                policy_forbidden=True,
                policy_reason_code="git_hook_facts_unavailable",
                facts_complete=False,
            )
        hooks_present = bool(hook_facts.hooks)
        return ToolRiskFacts(
            normalized_paths=arguments.paths,
            argv=("git", "commit"),
            cwd=".",
            recoverable=True,
            destructive=hooks_present,
            outside_workspace=outside,
            policy_forbidden=hooks_present and not self._workspace_trusted,
            policy_reason_code=(
                f"git_hook_facts:{hook_facts.facts_hash}" if hooks_present else None
            ),
            facts_complete=True,
        )

    def plan_action(
        self, run_id: str, arguments: GitCommitInput, *, action_id: str | None = None
    ) -> GitCommitPlan:
        if self._workspace_identity is None or self._policy_hash is None:
            raise GitCommitPlanError("git_policy_unbound")
        action_ids = arguments.action_ids or ((action_id,) if action_id else ())
        return GitCommitPlanBuilder(self._service()).build(
            run_id=run_id,
            action_ids=action_ids,
            workspace_identity=self._workspace_identity,
            paths=arguments.paths,
            message=arguments.message,
            verification_status=arguments.verification_status,
            policy_hash=self._policy_hash,
        )

    def execute_plan(self, plan: GitCommitPlan, arguments: GitCommitInput) -> ToolResult:
        if self.state_dir is None:
            return ToolResult(ok=False, error_code="git_state_unbound")
        try:
            result = GitCommitter(self._service(), state_dir=self.state_dir).execute(
                plan, arguments.message
            )
        except (GitCommitPlanError, GitCommitTransactionError) as exc:
            return ToolResult(ok=False, error_code=exc.code)
        return ToolResult(ok=True, content=result.model_dump(mode="json"))

    def execute(self, arguments: GitCommitInput) -> ToolResult:
        try:
            plan = self.plan_action("direct", arguments)
        except GitCommitPlanError as exc:
            return ToolResult(ok=False, error_code=exc.code)
        return self.execute_plan(plan, arguments)


class _GitBranchTool:
    operation: Literal["create", "switch"]
    name: str
    description: str
    input_model = GitBranchInput
    definition: ToolDefinitionV2

    def __init__(self, workspace: Path, *, environment: Mapping[str, str] | None = None) -> None:
        self.workspace = Path(workspace)
        self.environment = dict(environment) if environment is not None else os.environ.copy()
        self.service: GitService | None = None
        self.state_dir: Path | None = None
        self._workspace_identity: str | None = None
        self._policy_hash: str | None = None

        self.definition = ToolDefinitionV2(
            name=self.name,
            description=self.description,
            input_schema=GitBranchInput.model_json_schema(),
            tool_version=1,
            effects=(ToolEffect.WORKSPACE_WRITE, ToolEffect.PROCESS_EXECUTE),
            supports_cancellation=False,
            supports_recovery=True,
            max_output_bytes=100_000,
        )

    def bind_state(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)

    def bind_policy(
        self, workspace_identity: str, policy_hash: str, _trusted: bool = False
    ) -> None:
        self._workspace_identity = workspace_identity
        self._policy_hash = policy_hash

    def _service(self) -> GitService:
        if self.service is None:
            self.service = GitService(self.workspace, environment=self.environment)
        return self.service

    def risk_facts(self, arguments: GitBranchInput) -> ToolRiskFacts:
        return ToolRiskFacts(
            normalized_paths=(arguments.branch_name,),
            argv=("git", self.operation),
            cwd=".",
            recoverable=True,
            destructive=True,
            facts_complete=True,
        )

    def plan_action(
        self, run_id: str, arguments: GitBranchInput, *, action_id: str | None = None
    ) -> GitBranchPlan:
        if self._workspace_identity is None or self._policy_hash is None or action_id is None:
            raise GitBranchError("git_policy_unbound")
        return GitBranchPlanBuilder(self._service()).build(
            run_id=run_id,
            action_id=action_id,
            operation=self.operation,
            branch_name=arguments.branch_name,
            policy_hash=self._policy_hash,
        )

    def execute_plan(self, plan: GitBranchPlan, _arguments: GitBranchInput) -> ToolResult:
        if self.state_dir is None:
            return ToolResult(ok=False, error_code="git_state_unbound")
        try:
            result = GitBrancher(self._service(), state_dir=self.state_dir).execute(plan)
        except GitBranchError as exc:
            return ToolResult(ok=False, error_code=exc.code)
        return ToolResult(ok=True, content=result.model_dump(mode="json"))

    def execute(self, arguments: GitBranchInput) -> ToolResult:
        try:
            plan = self.plan_action("direct", arguments, action_id="direct")
        except GitBranchError as exc:
            return ToolResult(ok=False, error_code=exc.code)
        return self.execute_plan(plan, arguments)


class GitBranchCreateTool(_GitBranchTool):
    operation = "create"
    name = "git_branch_create"
    description = "Create one exact local branch without switching branches."


class GitBranchSwitchTool(_GitBranchTool):
    operation = "switch"
    name = "git_branch_switch"
    description = "Switch to one existing local branch after clean-state checks."
