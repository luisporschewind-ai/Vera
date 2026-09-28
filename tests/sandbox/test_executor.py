from pathlib import Path

import pytest

from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.sandbox.access import AccessSession
from vera.sandbox.files import PermissionPaths
from vera.sandbox.tools import RequestFileAccessTool
from vera.tools.builtin import ReadTool
from vera.tools.executor import ToolExecutor, ToolPreparationError
from vera.tools.file_mutation import WriteTool
from vera.tools.registry import ToolRegistry
from vera.workspace.mutation import FileMutationApplier, FileMutationStatus
from vera.workspace.paths import WorkspacePaths


def test_exact_once_approval_round_trip_and_no_recovery_grant(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "data.txt"
    outside.write_text("fake granted data")
    session = AccessSession(work)
    registry = ToolRegistry()
    registry.register(RequestFileAccessTool(session))
    registry.register(ReadTool(PermissionPaths(session), 1000))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    executor = ToolExecutor(
        registry, PolicyEngine(snapshot), permissions, access_session=session, goal_authorized=True
    )
    args = {"path": str(outside)}
    with pytest.raises(ToolPreparationError, match="file_access_approval_required"):
        executor.prepare(run_id="run", name="read", arguments=args)
    request = executor.prepare(
        run_id="run",
        name="request_file_access",
        arguments={
            "path": str(outside),
            "reason": "reuse data",
            "mode": "read",
            "scope": "once",
            "target_tool": "read",
            "target_arguments": args,
        },
    )
    assert request.policy_decision.decision.value == "approval_required"
    assert executor.execute_allowed(request).error_code == "approval_required"
    assert not session.grants()
    assert executor.execute_allowed(request, approved=True).ok
    read = executor.prepare(run_id="run", name="read", arguments=args)
    assert executor.execute_allowed(read).content == {"text": "fake granted data"}
    with pytest.raises(ToolPreparationError, match="file_access_approval_required"):
        executor.prepare(run_id="run", name="read", arguments=args)
    assert not AccessSession(work).grants()


def test_external_write_keeps_checkpoint_and_recovery_boundary(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "data.txt"
    outside.write_text("before")
    session = AccessSession(work)
    registry = ToolRegistry()
    registry.register(WriteTool(work, paths=PermissionPaths(session)))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    executor = ToolExecutor(
        registry,
        PolicyEngine(snapshot),
        permissions,
        access_session=session,
        goal_authorized=True,
        state_dir=tmp_path / "state",
    )
    args = {"path": str(outside), "content": "after"}
    with pytest.raises(ToolPreparationError):
        executor.prepare(run_id="run", name="write", arguments=args)
    req = session.request(outside, "read_write", "session")
    session.resolve(req.request_id, approved=True)
    prepared = executor.prepare(run_id="run", name="write", arguments=args)
    result = executor.execute_allowed(prepared, approved=True)
    assert result.ok, result
    assert outside.read_text() == "after"
    second = executor.prepare(
        run_id="run", name="write", arguments={"path": str(outside), "content": "after again"}
    )
    assert executor.execute_allowed(second, approved=True).ok
    assert outside.read_text() == "after again"
    assert prepared.mutation is not None
    recovery = FileMutationApplier(WorkspacePaths(work), tmp_path / "state")
    assert recovery.rollback(prepared.mutation.plan).status is FileMutationStatus.CONFLICTED
    assert outside.read_text() == "after again"
