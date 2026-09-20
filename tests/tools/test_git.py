from __future__ import annotations

from pathlib import Path

from vera.git.models import GitDiffRequest, GitLogRequest, GitShowRequest
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.tools.executor import ToolExecutor
from vera.tools.git import (
    GitBranchListTool,
    GitDiffTool,
    GitLogTool,
    GitShowTool,
    GitStatusTool,
)
from vera.tools.registry import ToolRegistry


def test_git_tools_declare_structured_read_effects() -> None:
    tools = (
        GitStatusTool(Path(".")),
        GitDiffTool(Path(".")),
        GitLogTool(Path(".")),
        GitShowTool(Path(".")),
        GitBranchListTool(Path(".")),
    )
    assert [tool.name for tool in tools] == [
        "git_status",
        "git_diff",
        "git_log",
        "git_show",
        "git_branch_list",
    ]
    for tool in tools:
        assert {effect.value for effect in tool.definition.effects} == {
            "workspace_read",
            "process_execute",
        }


def test_git_status_reports_non_repository_without_bootstrap_failure(tmp_path: Path) -> None:
    result = GitStatusTool(tmp_path).execute({})
    assert result.ok is False
    assert result.error_code == "git_not_repository"


def test_git_tool_inputs_are_contract_models() -> None:
    assert GitDiffTool.input_model.model_validate({"scope": "working"}) == GitDiffRequest(
        scope="working"
    )
    assert GitLogTool.input_model.model_validate({}) == GitLogRequest()
    assert GitShowTool.input_model.model_validate({"ref": "HEAD"}) == GitShowRequest(ref="HEAD")


def test_native_git_reads_are_auto_allowed_without_workspace_trust(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(GitStatusTool(tmp_path))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
    )
    executor = ToolExecutor(registry, PolicyEngine(snapshot), permissions)

    prepared = executor.prepare(run_id="run", name="git_status", arguments={})

    assert prepared.policy_decision.decision.value == "allow"
    assert prepared.policy_decision.reason_code == "native_git_read_allowed"
