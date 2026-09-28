from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from vera.contracts.process_actions import BashInput
from vera.contracts.tool_actions import ToolEffect
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import PermissionGrant, WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.process.supervisor import ProcessResult
from vera.tools.bash import BashTool, CommandActionPlan, classify_argv
from vera.tools.executor import ToolExecutor
from vera.tools.registry import ToolRegistry


class FakeSupervisor:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.requests = []

    def run(self, request, *, cancel_event=None):
        self.requests.append(request)
        return self.result


def test_bash_input_rejects_empty_nul_and_timeout_bounds() -> None:
    with pytest.raises(ValidationError):
        BashInput(argv=())
    with pytest.raises(ValidationError):
        BashInput(argv=("printf", "bad\x00value"))
    with pytest.raises(ValidationError):
        BashInput(argv=("printf",), timeout_seconds=0)
    with pytest.raises(ValidationError):
        BashInput(argv=("printf",), timeout_seconds=1801)


def test_bash_input_does_not_parse_shell_syntax() -> None:
    item = BashInput(argv=("printf", "a | b $(echo no) *.txt"))
    assert item.argv[1] == "a | b $(echo no) *.txt"
    assert classify_argv(item.argv)["executable"] == "printf"


def test_bash_classifies_git_writes_as_native_git_tool_bypass() -> None:
    facts = classify_argv(("git", "commit", "-m", "message"))
    assert facts["writes"] is True
    assert facts["git_write"] is True
    assert facts["forbidden"] is True
    risk = BashTool(Path(".")).risk_facts(BashInput(argv=("git", "commit", "-m", "message")))
    assert risk.policy_reason_code == "use_native_git_tool"


def test_bash_rejects_workspace_escape_and_non_directory(tmp_path: Path) -> None:
    tool = BashTool(tmp_path, FakeSupervisor(ProcessResult("exited", 0, b"", b"")))
    with pytest.raises(ValueError):
        tool.normalized_cwd(BashInput(argv=("pwd",), cwd="../outside"))
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="cwd_not_directory"):
        tool.normalized_cwd(BashInput(argv=("pwd",), cwd="file.txt"))


def test_bash_uses_supervisor_shell_false_contract_and_decodes_output(tmp_path: Path) -> None:
    supervisor = FakeSupervisor(
        ProcessResult("exited", 0, b"ok\xff", b"warn", stdout_truncated=True)
    )
    tool = BashTool(tmp_path, supervisor, environment_source={"PATH": "/bin", "API_KEY": "secret"})
    result = tool.execute(BashInput(argv=("printf", "a | b")))
    assert result.ok is True
    assert result.truncated is True
    assert result.content["stdout"] == "ok�"
    request = supervisor.requests[0]
    assert request.argv == ("printf", "a | b")
    assert request.cwd == tmp_path.resolve()
    assert "API_KEY" not in request.env


def test_bash_result_maps_timeout_and_exit_errors(tmp_path: Path) -> None:
    timeout = BashTool(tmp_path, FakeSupervisor(ProcessResult("timed_out", None, b"", b"")))
    assert timeout.execute(BashInput(argv=("sleep", "1"))).error_code == "timeout"
    failed = BashTool(tmp_path, FakeSupervisor(ProcessResult("exited", 2, b"", b"no")))
    result = failed.execute(BashInput(argv=("false",)))
    assert result.ok is False
    assert result.error_code == "process_exit"


def test_bash_plan_has_stable_action_facts(tmp_path: Path) -> None:
    tool = BashTool(tmp_path)
    plan = tool.plan_action("run-1", BashInput(argv=("pytest", "-q")), action_id="action-1")
    assert isinstance(plan, CommandActionPlan)
    assert plan.cwd == "."
    assert plan.executable == "pytest"
    assert plan.risk_level.value == "low"
    assert plan.policy_hash == "0" * 64


def test_bash_executor_binds_plan_and_denies_shell_or_deletion(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=2,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
    )
    executor = ToolExecutor(registry, PolicyEngine(snapshot), permissions, goal_authorized=True)
    safe = executor.prepare(run_id="run", name="bash", arguments={"argv": ["pwd"]})
    assert safe.action.effects == (ToolEffect.PROCESS_EXECUTE,)
    assert safe.policy_decision.decision.value == "allow"
    assert executor.execute_allowed(safe).ok is True
    denied = executor.prepare(
        run_id="run", name="bash", arguments={"argv": ["bash", "-c", "echo hi"]}
    )
    assert denied.policy_decision.decision.value == "deny"
    assert executor.execute_allowed(denied, approved=True).error_code == "policy_denied"


def test_bash_run_grant_cannot_bypass_native_git_write_boundary(tmp_path: Path) -> None:
    grant = PermissionGrant(
        grant_id="run-grant",
        scope="run",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE, ToolEffect.WORKSPACE_WRITE),
        argument_constraints={
            "argv": ["git", "commit", "-m", "x"],
            "cwd": ".",
            "timeout_seconds": 120,
        },
        run_id="run-1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=2,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=False,
        grants=(grant,),
    )
    executor = ToolExecutor(registry, PolicyEngine(snapshot), permissions, goal_authorized=False)

    allowed = executor.prepare(
        run_id="run-1", name="bash", arguments={"argv": ["git", "commit", "-m", "x"]}
    )
    other_run = executor.prepare(
        run_id="run-2", name="bash", arguments={"argv": ["git", "commit", "-m", "x"]}
    )
    changed_argv = executor.prepare(
        run_id="run-1", name="bash", arguments={"argv": ["git", "commit", "-m", "y"]}
    )

    assert allowed.policy_decision.decision.value == "deny"
    assert allowed.policy_decision.reason_code == "risk_forbidden"
    assert other_run.policy_decision.decision.value == "deny"
    assert changed_argv.policy_decision.decision.value == "deny"


def test_bash_workspace_grant_does_not_relax_forbidden_shell(tmp_path: Path) -> None:
    grant = PermissionGrant(
        grant_id="workspace-grant",
        scope="workspace",
        tool_name="bash",
        effects=(ToolEffect.PROCESS_EXECUTE,),
        argument_constraints={"argv": ["bash", "-c", "echo hi"]},
    )
    registry = ToolRegistry()
    registry.register(BashTool(tmp_path))
    snapshot = EffectivePolicySnapshotV2(workspace_identity="workspace")
    permissions = WorkspacePermissionSnapshot(
        workspace_identity="workspace",
        policy_major_version=2,
        protected_roots_hash=snapshot.protected_roots_hash,
        trusted=True,
        grants=(grant,),
    )
    executor = ToolExecutor(registry, PolicyEngine(snapshot), permissions, goal_authorized=True)

    prepared = executor.prepare(
        run_id="run-1", name="bash", arguments={"argv": ["bash", "-c", "echo hi"]}
    )

    assert prepared.policy_decision.decision.value == "deny"
    assert prepared.policy_decision.reason_code == "risk_forbidden"


def test_bash_reports_cleanup_failure_without_hiding_execution(tmp_path: Path) -> None:
    completed = ProcessResult(
        "error", 0, b"build passed", b"cleanup failed", cleanup_error="sandbox_cleanup_failed"
    )
    result = BashTool(tmp_path, supervisor=FakeSupervisor(completed)).execute(
        BashInput(argv=("/bin/echo", "fixture"))
    )
    assert not result.ok
    assert result.error_code == "sandbox_cleanup_failed"
    assert result.content["exit_code"] == 0
    assert result.content["stdout"] == "build passed"
