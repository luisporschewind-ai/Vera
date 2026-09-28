from pathlib import Path

from pydantic import BaseModel

from vera.contracts.commands import ResolveApproval, ResumeRun, StartRun
from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.policy.engine import PolicyEngine
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.runtime.engine import VeraRuntime
from vera.tools.builtin import ReadTool
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.registry import ToolRegistry
from vera.workspace.paths import WorkspacePaths


class ApprovalInput(BaseModel):
    path: str


class ApprovalTool:
    name = "approval_tool"
    input_model = ApprovalInput
    definition = ToolDefinitionV2(
        name=name,
        description="test approval boundary",
        input_schema=ApprovalInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_WRITE,),
        supports_cancellation=False,
        supports_recovery=True,
        max_output_bytes=100,
    )

    def __init__(self) -> None:
        self.calls = 0

    def risk_facts(self, _arguments: ApprovalInput) -> ToolRiskFacts:
        return ToolRiskFacts(
            normalized_paths=("output.txt",),
            facts_complete=True,
            recoverable=False,
        )

    def execute(self, _arguments: ApprovalInput) -> ToolResult:
        self.calls += 1
        return ToolResult(ok=True, content={"done": True})


def test_runtime_uses_executor_not_legacy_registry_dispatch(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    registry = ToolRegistry()
    registry.register(ReadTool(WorkspacePaths(tmp_path), 100))
    monkeypatch.setattr(
        registry,
        "execute",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy dispatch")),
    )
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
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
                ModelTurn(assistant_text="已读取。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
    )

    events = list(
        runtime.handle(StartRun(goal="读取 hello", workspace_root=tmp_path, model_profile="fake"))
    )

    assert [event.type for event in events if event.type.startswith("tool.")] == [
        "tool.started",
        "tool.policy_decided",
        "tool.action_prepared",
        "tool.completed",
    ]
    assert events[-1].payload["outcome"] == "responded"
    assert [tool.name for tool in runtime.adapter.requests[0].tools] == ["read"]


def test_runtime_does_not_rebind_explicit_policy_to_current_workspace(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    registry = ToolRegistry()
    registry.register(ReadTool(WorkspacePaths(tmp_path), 100))
    explicit_policy = PolicyEngine(EffectivePolicySnapshotV2(workspace_identity="other"))
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="read-mismatch",
                            name="read",
                            arguments={"path": "hello.txt"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="策略拒绝。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
        policy_engine=explicit_policy,
    )

    events = list(
        runtime.handle(StartRun(goal="读取 hello", workspace_root=tmp_path, model_profile="fake"))
    )

    completed = next(event for event in events if event.type == "tool.completed")
    assert completed.payload["ok"] is False
    assert completed.payload["error_code"] == "policy_denied"


def test_runtime_pauses_high_risk_tool_before_implementation(tmp_path: Path) -> None:
    tool = ApprovalTool()
    registry = ToolRegistry()
    registry.register(tool)
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="approval-1",
                            name="approval_tool",
                            arguments={"path": "output.txt"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="已完成。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
    )

    events = list(
        runtime.handle(StartRun(goal="执行写入", workspace_root=tmp_path, model_profile="fake"))
    )

    required = next(event for event in events if event.type == "approval.required")
    assert required.payload["kind"] == "tool"
    assert required.payload["action_id"]
    assert required.payload["input_hash"]
    assert required.payload["target_facts_hash"]
    assert tool.calls == 0


def test_runtime_revalidates_and_executes_approved_tool(tmp_path: Path) -> None:
    tool = ApprovalTool()
    registry = ToolRegistry()
    registry.register(tool)
    runtime = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="approval-2",
                            name="approval_tool",
                            arguments={"path": "output.txt"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="已完成。", finish_reason="stop"),
            ]
        ),
        registry,
        tmp_path / "state",
    )
    first = list(
        runtime.handle(StartRun(goal="执行写入", workspace_root=tmp_path, model_profile="fake"))
    )
    required = next(event for event in first if event.type == "approval.required")
    resolved = list(
        runtime.handle(
            ResolveApproval(
                run_id=required.payload["run_id"],
                approval_id=required.payload["approval_id"],
                target_hash=required.payload["target_hash"],
                decision="approve",
            )
        )
    )
    assert any(event.type == "approval.resolved" for event in resolved)
    assert tool.calls == 1


def test_approved_tool_plan_survives_resume_and_revalidation(tmp_path: Path) -> None:
    tool = ApprovalTool()
    registry = ToolRegistry()
    registry.register(tool)
    state_dir = tmp_path / "state"
    first = VeraRuntime(
        FakeModelAdapter(
            [
                ModelTurn(
                    finish_reason="tool_calls",
                    tool_calls=(
                        ModelToolCall(
                            call_id="approval-3",
                            name="approval_tool",
                            arguments={"path": "output.txt"},
                        ),
                    ),
                ),
                ModelTurn(assistant_text="已完成。", finish_reason="stop"),
            ]
        ),
        registry,
        state_dir,
        installation_id="install-1",
    )
    initial = list(
        first.handle(StartRun(goal="执行写入", workspace_root=tmp_path, model_profile="fake"))
    )
    required = next(event for event in initial if event.type == "approval.required")
    snapshot = RecoverySnapshotStore(state_dir).load(required.run_id)
    assert snapshot.pending_tool_action is not None

    second = VeraRuntime(
        FakeModelAdapter([ModelTurn(assistant_text="已完成。", finish_reason="stop")]),
        registry,
        state_dir,
        installation_id="install-1",
        snapshot_store=RecoverySnapshotStore(state_dir),
    )
    resumed = list(second.handle(ResumeRun(run_id=required.run_id)))
    resumed_required = next(event for event in resumed if event.type == "approval.required")
    resolved = list(
        second.handle(
            ResolveApproval(
                run_id=required.run_id,
                approval_id=resumed_required.payload["approval_id"],
                target_hash=resumed_required.payload["target_hash"],
                decision="approve",
            )
        )
    )
    assert any(event.type == "approval.resolved" for event in resolved)
    assert tool.calls == 1
