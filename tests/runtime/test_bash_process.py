from pathlib import Path

from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.process.supervisor import ProcessResult
from vera.recovery.probe import workspace_identity
from vera.runtime.engine import VeraRuntime
from vera.tools.bash import BashTool
from vera.tools.registry import ToolRegistry


class RecordingSupervisor:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, _request, *, cancel_event=None) -> ProcessResult:
        del cancel_event
        self.calls += 1
        return ProcessResult(status="exited", exit_code=0, stdout=b"ok\n", stderr=b"")


def _runtime(tmp_path: Path, supervisor: RecordingSupervisor) -> VeraRuntime:
    identity = workspace_identity(tmp_path, "install-test")
    snapshot = EffectivePolicySnapshotV2(workspace_identity=identity)
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path, supervisor))
    return VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="bash-1",
                            name="bash",
                            arguments={"argv": ["git", "commit", "-m", "x"]},
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
            trusted=False,
        ),
    )


def test_bash_git_write_is_denied_without_process_execution(tmp_path: Path) -> None:
    supervisor = RecordingSupervisor()
    runtime = _runtime(tmp_path, supervisor)
    initial = list(
        runtime.handle(StartRun(goal="执行本地命令", workspace_root=tmp_path, model_profile="fake"))
    )
    completed = next(event for event in initial if event.type == "tool.completed")
    assert supervisor.calls == 0
    assert supervisor.calls == 0
    assert completed.payload["ok"] is False
    assert completed.payload["error_code"] == "policy_denied"
