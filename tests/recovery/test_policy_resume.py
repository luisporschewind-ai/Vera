"""Recovery reclassification against current policy."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.commands import ResumeRun
from vera.models.base import FakeModelAdapter
from vera.policy.engine import PolicyEngine
from vera.policy.snapshot import EffectivePolicySnapshot
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry


def test_resume_with_matching_policy_engine_constructs(tmp_path: Path) -> None:
    state = tmp_path / "state"
    engine = PolicyEngine(
        EffectivePolicySnapshot(workspace_identity="ws", user_allowed_command_prefixes=())
    )
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        state,
        command_policy=CommandPolicy((), policy_engine=engine),
        policy_engine=engine,
        installation_id="install",
    )
    events = tuple(runtime.handle(ResumeRun(run_id="missing")))
    assert events
    assert events[-1].type in {"recovery.manual_required", "recovery.detected"}
