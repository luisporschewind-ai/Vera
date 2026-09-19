import pytest
from pydantic import BaseModel

from vera.contracts.tool_actions import ToolEffect, ToolRiskFacts
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.tools.definitions import ToolDefinitionV2, ToolResult
from vera.tools.executor import ToolExecutor, ToolPreparationError
from vera.tools.registry import ToolRegistry


class EchoInput(BaseModel):
    path: str


class EchoTool:
    name = "echo"
    input_model = EchoInput
    definition = ToolDefinitionV2(
        name=name,
        description="A harmless test read.",
        input_schema=EchoInput.model_json_schema(),
        tool_version=1,
        effects=(ToolEffect.WORKSPACE_READ,),
        supports_cancellation=False,
        supports_recovery=False,
        max_output_bytes=100,
    )

    def __init__(self) -> None:
        self.calls = 0
        self.stale = False

    def risk_facts(self, arguments: EchoInput) -> ToolRiskFacts:
        return ToolRiskFacts(
            normalized_paths=(arguments.path,),
            outside_workspace=self.stale,
            facts_complete=True,
        )

    def execute(self, arguments: EchoInput) -> ToolResult:
        self.calls += 1
        return ToolResult(ok=True, content={"path": arguments.path})


def _executor(tool: EchoTool | None = None) -> tuple[ToolExecutor, EchoTool]:
    registered = tool or EchoTool()
    registry = ToolRegistry()
    registry.register(registered)
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=snapshot.builtin_policy_version,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
    )
    return ToolExecutor(registry, PolicyEngine(snapshot), permissions), registered


def test_prepare_rejects_unknown_tool_and_invalid_schema_without_execution() -> None:
    executor, tool = _executor()
    with pytest.raises(ToolPreparationError, match="unknown_tool"):
        executor.prepare(run_id="run", name="missing", arguments={})
    with pytest.raises(ToolPreparationError, match="invalid_tool_arguments"):
        executor.prepare(run_id="run", name="echo", arguments={})
    assert tool.calls == 0


def test_prepare_requires_approval_or_denies_without_execution() -> None:
    executor, tool = _executor()
    prepared = executor.prepare(run_id="run", name="echo", arguments={"path": "a.txt"})
    assert prepared.policy_decision.decision.value == "allow"
    tool.stale = True
    result = executor.execute_allowed(prepared)
    assert result.ok is False
    assert result.error_code == "stale_tool_action"
    assert tool.calls == 0


def test_approval_and_deny_never_call_the_implementation() -> None:
    executor, tool = _executor()
    tool.stale = True
    denied = executor.prepare(run_id="run", name="echo", arguments={"path": "../outside"})
    assert denied.policy_decision.decision.value == "deny"
    assert executor.execute_allowed(denied).error_code == "policy_denied"
    assert tool.calls == 0


def test_execute_allowed_rechecks_facts_before_calling_implementation() -> None:
    executor, tool = _executor()
    prepared = executor.prepare(run_id="run", name="echo", arguments={"path": "a.txt"})
    assert executor.execute_allowed(prepared).content == {"path": "a.txt"}
    assert tool.calls == 1


def test_execute_allowed_bounds_oversized_result() -> None:
    executor, tool = _executor()
    tool.definition = tool.definition.model_copy(update={"max_output_bytes": 1})
    prepared = executor.prepare(run_id="run", name="echo", arguments={"path": "a.txt"})
    result = executor.execute_allowed(prepared)
    assert result.ok is False
    assert result.truncated is True
    assert result.error_code == "output_limit_exceeded"
