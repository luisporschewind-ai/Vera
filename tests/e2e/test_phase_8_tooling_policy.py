from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import (
    PROJECT_KINDS,
    allowed_python_policy,
    copy_representative_project,
    tool_registry_for,
    turns_for,
)
from vera.contracts.commands import ResolveApproval, StartRun
from vera.contracts.compatibility import current_compatibility_manifest
from vera.models.base import FakeModelAdapter
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.runtime.engine import VeraRuntime
from vera.tools.bash import BashTool
from vera.tools.builtin import FindTool, GrepTool, LsTool, ReadTool
from vera.tools.executor import ToolExecutor
from vera.tools.file_mutation import EditTool
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


def test_phase8_manifest_and_canonical_tool_names_are_stable(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path)
    registry = ToolRegistry()
    for tool in (
        ReadTool(paths, 100_000),
        EditTool(tmp_path, tmp_path / "state"),
        GrepTool(paths),
        FindTool(paths),
        LsTool(paths),
        BashTool(tmp_path),
    ):
        registry.register(tool)

    assert {item.name for item in registry.definitions()} == {
        "bash",
        "edit",
        "find",
        "grep",
        "ls",
        "read",
    }
    contract_names = {item.name for item in current_compatibility_manifest().tooling_contracts}
    assert {"ToolDefinitionV2", "ToolAction", "FileMutationPlan"} <= contract_names


def test_phase8_bash_policy_matrix_has_allow_and_forbidden_boundaries(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="phase8-workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="phase8-workspace",
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        goal_authorized=True,
    )

    allowed = executor.prepare(run_id="run", name="bash", arguments={"argv": ["pwd"]})
    shell = executor.prepare(
        run_id="run", name="bash", arguments={"argv": ["sh", "-c", "echo unsafe"]}
    )
    git_write = executor.prepare(
        run_id="run",
        name="bash",
        arguments={"argv": ["git", "push", "origin", "main"]},
    )

    assert allowed.policy_decision.decision.value == "allow"
    assert executor.execute_allowed(allowed).ok is True
    assert shell.policy_decision.decision.value == "deny"
    assert git_write.policy_decision.decision.value == "deny"
    assert executor.execute_allowed(git_write, approved=True).error_code == "policy_denied"


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_phase8_representative_project_edit_and_rejection_matrix(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / kind
    project = copy_representative_project(kind, workspace)
    runtime = VeraRuntime(
        FakeModelAdapter(turns_for(project, "single")),
        tool_registry_for(workspace),
        tmp_path / f"{kind}-state",
        command_policy=allowed_python_policy(),
        installation_id="phase8",
    )
    events = list(
        runtime.handle(
            StartRun(
                goal="implement the requested change",
                workspace_root=workspace,
                model_profile="fake",
            )
        )
    )
    approval = next(event for event in events if event.type == "approval.required")
    completed = list(
        runtime.handle(
            ResolveApproval(
                run_id=approval.run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )

    assert completed[-1].type == "run.completed"
    assert (workspace / project.single_path).read_text(encoding="utf-8") == project.single_after
