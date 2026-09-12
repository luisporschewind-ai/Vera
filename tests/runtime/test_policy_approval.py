"""Policy-bound approval invalidation tests."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.commands import ResolveApproval, StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.policy.engine import PolicyEngine
from vera.policy.snapshot import EffectivePolicySnapshot
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry


def _proposal() -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id="1",
                name="propose_changeset",
                arguments={
                    "summary": "edit",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": "new\n",
                        }
                    ],
                },
            ),
        ),
    )


def test_changed_policy_invalidates_pending_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    state = tmp_path / "state"
    first_engine = PolicyEngine(
        EffectivePolicySnapshot(
            workspace_identity="ws",
            user_allowed_command_prefixes=(("pytest",),),
        )
    )
    first = VeraRuntime(
        FakeModelAdapter([_proposal()]),
        ToolRegistry(),
        state,
        command_policy=CommandPolicy((("pytest",),), policy_engine=first_engine),
        policy_engine=first_engine,
        installation_id="install",
    )
    approval = next(
        event
        for event in first.handle(
            StartRun(goal="edit", workspace_root=workspace, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    second_engine = PolicyEngine(
        EffectivePolicySnapshot(
            workspace_identity="ws",
            user_allowed_command_prefixes=(("ruff",),),
        )
    )
    # Reuse in-memory run with a different engine to simulate policy drift.
    first.policy_engine = second_engine
    first.command_policy = CommandPolicy((("ruff",),), policy_engine=second_engine)
    events = tuple(
        first.handle(
            ResolveApproval(
                run_id=approval.run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    assert events[-1].type == "approval.invalidated"
    assert events[-1].payload["reason_code"] == "policy_changed"
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_changed_security_context_invalidates_pending_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime = VeraRuntime(
        FakeModelAdapter([_proposal()]),
        ToolRegistry(),
        tmp_path / "state",
        installation_id="install",
    )
    approval = next(
        event
        for event in runtime.handle(
            StartRun(goal="edit", workspace_root=workspace, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    context = runtime.runs[approval.run_id]
    context.security_context_hash = "b" * 64
    events = tuple(
        runtime.handle(
            ResolveApproval(
                run_id=approval.run_id,
                approval_id=str(approval.payload["approval_id"]),
                target_hash=str(approval.payload["target_hash"]),
                decision="approve",
            )
        )
    )
    assert events[-1].type == "approval.invalidated"
    assert events[-1].payload["reason_code"] == "security_context_changed"
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
