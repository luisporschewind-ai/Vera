from pathlib import Path

from vera.contracts.commands import ResolveApproval, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.recovery.probe import workspace_identity
from vera.runtime.engine import VeraRuntime
from vera.tools.builtin import ReadTool
from vera.tools.file_mutation import EditTool, WriteTool
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


def runtime(tmp_path: Path, *, trusted: bool) -> VeraRuntime:
    identity = workspace_identity(tmp_path, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    registry = ToolRegistry()
    registry.register(WriteTool(tmp_path))
    registry.register(EditTool(tmp_path))
    return VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="write-1",
                            name="write",
                            arguments={"path": "hello.txt", "content": "hello\n"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="完成。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
        installation_id="install-test",
        policy_engine=PolicyEngine(snapshot),
        workspace_permissions=WorkspacePermissionSnapshot(
            workspace_identity=identity,
            policy_major_version=snapshot.builtin_policy_version,
            protected_roots_hash=snapshot.protected_roots_hash,
            trusted=trusted,
        ),
    )


def test_trusted_goal_write_applies_without_approval(tmp_path: Path) -> None:
    events = list(
        runtime(tmp_path, trusted=True).handle(
            StartRun(goal="实现功能并修改代码", workspace_root=tmp_path, model_profile="fake")
        )
    )

    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello\n"
    assert not any(event.type == "approval.required" for event in events)
    assert any(event.type == "file_mutation.planned" for event in events)
    assert any(event.type == "file_mutation.applied" for event in events)
    prepared = next(event for event in events if event.type == "tool.action_prepared")
    planned = next(event for event in events if event.type == "file_mutation.planned")
    assert prepared.payload["action_id"] == planned.payload["action_id"]


def test_untrusted_write_creates_exact_approval_and_snapshot(tmp_path: Path) -> None:
    runtime_instance = runtime(tmp_path, trusted=False)
    events = list(
        runtime_instance.handle(
            StartRun(goal="实现功能并修改代码", workspace_root=tmp_path, model_profile="fake")
        )
    )

    required = next(event for event in events if event.type == "approval.required")
    assert required.payload["kind"] == "tool"
    assert not (tmp_path / "hello.txt").exists()
    snapshot = RecoverySnapshotStore(tmp_path / "state").load(required.run_id)
    assert snapshot.pending_tool_action is not None

    resolved = list(
        runtime_instance.handle(
            ResolveApproval(
                run_id=required.run_id,
                approval_id=required.payload["approval_id"],
                target_hash=required.payload["target_hash"],
                decision="approve",
            )
        )
    )
    assert any(event.type == "file_mutation.applied" for event in resolved)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello\n"


def test_run_can_apply_multiple_mutations_and_return_each_tool_result(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    identity = workspace_identity(tmp_path, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    registry = ToolRegistry()
    registry.register(ReadTool(WorkspacePaths(tmp_path), 100))
    registry.register(EditTool(tmp_path))
    registry.register(WriteTool(tmp_path))
    runtime_instance = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="edit-1",
                            name="edit",
                            arguments={"path": "hello.txt", "old_text": "old", "new_text": "new"},
                        ),
                    ),
                ),
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="read-1",
                            name="read",
                            arguments={"path": "hello.txt"},
                        ),
                    ),
                ),
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="write-1",
                            name="write",
                            arguments={"path": "second.txt", "content": "second\n"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="完成。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
        installation_id="install-test",
        policy_engine=PolicyEngine(snapshot),
        workspace_permissions=WorkspacePermissionSnapshot(
            workspace_identity=identity,
            policy_major_version=snapshot.builtin_policy_version,
            protected_roots_hash=snapshot.protected_roots_hash,
            trusted=True,
        ),
    )

    events = list(
        runtime_instance.handle(
            StartRun(goal="实现功能并运行验证", workspace_root=tmp_path, model_profile="fake")
        )
    )

    applied = [event for event in events if event.type == "file_mutation.applied"]
    assert len(applied) == 2
    assert {item["path"] for item in applied[-1].payload["cumulative_diff"]} == {
        "hello.txt",
        "second.txt",
    }
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "second.txt").read_text(encoding="utf-8") == "second\n"
