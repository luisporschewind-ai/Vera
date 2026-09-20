from __future__ import annotations

from pathlib import Path

import pytest

from tests.git.conftest import run_git
from vera.contracts.commands import StartRun
from vera.models.base import FakeModelAdapter, ModelToolCall
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.policy.engine import PolicyEngine
from vera.policy.permissions import WorkspacePermissionSnapshot
from vera.policy.snapshot import EffectivePolicySnapshotV2
from vera.recovery.probe import workspace_identity
from vera.redaction import Redactor
from vera.runtime.approval import ApprovalGate
from vera.runtime.context import RunContext
from vera.runtime.engine import VeraRuntime
from vera.runtime.state import RunStateMachine
from vera.tools.executor import ToolExecutor
from vera.tools.git import GitCommitTool
from vera.tools.registry import ToolRegistry


def _repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    env = {
        "GIT_AUTHOR_NAME": "Vera Test",
        "GIT_AUTHOR_EMAIL": "vera-test@example.invalid",
        "GIT_COMMITTER_NAME": "Vera Test",
        "GIT_COMMITTER_EMAIL": "vera-test@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "LANG": "C",
    }
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init", "--quiet", env=env)
    (repository / "README.md").write_text("initial\n", encoding="utf-8")
    run_git(repository, "add", "--", "README.md", env=env)
    run_git(repository, "commit", "--quiet", "-m", "initial", env=env)
    run_git(repository, "config", "user.name", "Vera Test", env=env)
    run_git(repository, "config", "user.email", "vera-test@example.invalid", env=env)
    return repository, env


def _setup(tmp_path: Path) -> tuple[VeraRuntime, RunContext, ToolExecutor, object, ModelToolCall]:
    repository, env = _repo(tmp_path)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")
    identity = workspace_identity(repository, "install-test")
    policy = EffectivePolicySnapshotV2(workspace_identity=identity)
    permissions = WorkspacePermissionSnapshot(
        workspace_identity=identity,
        policy_major_version=policy.builtin_policy_version,
        protected_roots_hash=policy.protected_roots_hash,
        trusted=True,
    )
    registry = ToolRegistry()
    registry.register(GitCommitTool(repository, environment=env))
    executor = ToolExecutor(
        registry,
        PolicyEngine(policy),
        permissions,
        goal_authorized=True,
        state_dir=tmp_path / "state",
    )
    prepared = executor.prepare(
        run_id="run-git",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-git"],
            "verification_status": "passed",
        },
    )
    command = StartRun(goal="commit", workspace_root=repository, model_profile="fake")
    context = RunContext(
        run_id="run-git",
        command=command,
        machine=RunStateMachine(),
        journal=EventJournal(tmp_path / "state", "run-git", Redactor([])),
        messages=[],
        approval_gate=ApprovalGate("run-git"),
    )
    runtime = VeraRuntime(FakeModelAdapter([]), registry, tmp_path / "state")
    call = ModelToolCall(
        call_id="call-git",
        name="git_commit",
        arguments={
            "paths": ["app.py"],
            "message": "Add app",
            "action_ids": ["action-git"],
            "verification_status": "passed",
        },
    )
    return runtime, context, executor, prepared, call


def test_git_crash_leaves_pending_facts_in_recovery_snapshot(tmp_path: Path) -> None:
    runtime, context, _executor, prepared, call = _setup(tmp_path)

    class CrashExecutor(ToolExecutor):
        def execute_allowed(self, prepared, *, approved=False):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated crash")

    with pytest.raises(RuntimeError, match="simulated crash"):
        runtime._execute_prepared_tool(  # noqa: SLF001
            context, call, CrashExecutor.__new__(CrashExecutor), prepared
        )

    snapshot = RecoverySnapshotStore(tmp_path / "state").load("run-git")
    assert snapshot.pending_git_operation is not None
    assert snapshot.pending_git_operation.operation == "git_commit"
    assert snapshot.pending_git_operation.paths == ("app.py",)
    assert snapshot.pending_git_operation.commit_message_hash
    assert [event.type for event in context.journal.read_all()] == ["git.operation.started"]


def test_git_completion_clears_pending_facts_and_emits_terminal_event(tmp_path: Path) -> None:
    runtime, context, executor, prepared, call = _setup(tmp_path)

    result, events = runtime._execute_prepared_tool(  # noqa: SLF001
        context, call, executor, prepared
    )

    assert result.ok is True
    assert [event.type for event in events[:2]] == [
        "git.operation.started",
        "git.operation.completed",
    ]
    assert context.pending_git_operation is None
    snapshot = RecoverySnapshotStore(tmp_path / "state").load("run-git")
    assert snapshot.pending_git_operation is None
