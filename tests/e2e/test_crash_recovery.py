from __future__ import annotations

from pathlib import Path

import pytest

from vera.contracts.commands import ResolveApproval, ResumeRun, StartRun
from vera.contracts.recovery import RecoveryClassification, RecoveryStage
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry
from vera.workspace.apply import AtomicFileWriter, SimulatedCrash


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
                            "after_content": "new-hello\n",
                        },
                        {
                            "operation": "create",
                            "path": "extra.txt",
                            "after_content": "new-extra\n",
                        },
                    ],
                    "verification": [
                        {"argv": ["ruff", "check", "."], "cwd": "."},
                        {"argv": ["ruff", "format", "--check", "."], "cwd": "."},
                    ],
                },
            ),
        ),
    )


class CrashSnapshotStore(RecoverySnapshotStore):
    def __init__(self, state_dir: Path, failpoint: str) -> None:
        super().__init__(state_dir)
        self.failpoint = failpoint

    def save(self, snapshot):  # type: ignore[no-untyped-def]
        super().save(snapshot)
        if self.failpoint == "changeset_approval" and (
            snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL
        ):
            raise SimulatedCrash(self.failpoint)
        if self.failpoint == "checkpoint" and snapshot.stage is RecoveryStage.CHECKPOINT_READY:
            raise SimulatedCrash(self.failpoint)
        if (
            self.failpoint == "changeset_applied"
            and snapshot.stage is RecoveryStage.VERIFYING
            and snapshot.verification_index == 0
            and not snapshot.verification_in_flight
        ):
            raise SimulatedCrash(self.failpoint)
        if self.failpoint == "verification_started" and snapshot.verification_in_flight:
            raise SimulatedCrash(self.failpoint)
        if (
            self.failpoint == "verification_completed"
            and snapshot.stage is RecoveryStage.VERIFYING
            and snapshot.verification_index == 1
            and not snapshot.verification_in_flight
        ):
            raise SimulatedCrash(self.failpoint)


class CrashAfterFirstWrite(AtomicFileWriter):
    def __init__(self) -> None:
        self._writes = 0

    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
        self._writes += 1
        if self._writes >= 2:
            raise SimulatedCrash("apply_file")
        super().replace(path, content, mode)


def _policy() -> CommandPolicy:
    return CommandPolicy(user_allowed_prefixes=(("ruff",),))


def _runtime(
    tmp_path: Path,
    *,
    failpoint: str | None = None,
    writer: CrashAfterFirstWrite | None = None,
) -> VeraRuntime:
    store: RecoverySnapshotStore
    if failpoint and failpoint != "apply_file":
        store = CrashSnapshotStore(tmp_path / "state", failpoint)
    else:
        store = RecoverySnapshotStore(tmp_path / "state")
    return VeraRuntime(
        FakeModelAdapter([_proposal()]),
        ToolRegistry(),
        tmp_path / "state",
        command_policy=_policy(),
        snapshot_store=store,
        installation_id="install-1",
        file_writer=writer,
        artifact_prefix=tmp_path / "vera-verification",
    )


def _approve_until_crash(runtime: VeraRuntime, workspace: Path) -> str:
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=workspace, model_profile="fake"))
    )
    run_id = events[0].run_id
    while True:
        approval = next(
            (event for event in reversed(events) if event.type == "approval.required"),
            None,
        )
        if approval is None:
            return run_id
        events = list(
            runtime.handle(
                ResolveApproval(
                    run_id=run_id,
                    approval_id=str(approval.payload["approval_id"]),
                    target_hash=str(approval.payload["target_hash"]),
                    decision="approve",
                )
            )
        )


EXPECTED = {
    "changeset_approval": RecoveryClassification.RESUMABLE_APPROVAL,
    "checkpoint": RecoveryClassification.SAFE_TO_ABANDON,
    "apply_file": RecoveryClassification.RECOVERABLE_PARTIAL_APPLY,
    "changeset_applied": RecoveryClassification.RESUMABLE_VERIFICATION,
    "verification_started": RecoveryClassification.MANUAL_REQUIRED,
    "verification_completed": RecoveryClassification.RESUMABLE_VERIFICATION,
}


@pytest.mark.parametrize("failpoint", list(EXPECTED))
def test_crash_recovery_classifies_across_new_runtime(tmp_path: Path, failpoint: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    writer = CrashAfterFirstWrite() if failpoint == "apply_file" else None
    first = _runtime(tmp_path, failpoint=failpoint, writer=writer)
    with pytest.raises(SimulatedCrash, match=failpoint):
        _approve_until_crash(first, workspace)

    run_id = next(iter(first.runs))
    del first
    second = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        tmp_path / "state",
        command_policy=_policy(),
        snapshot_store=RecoverySnapshotStore(tmp_path / "state"),
        installation_id="install-1",
        artifact_prefix=tmp_path / "vera-verification",
    )
    reports = second.coordinator.scan(run_id)
    assert len(reports) == 1
    report = reports[0]
    assert report.classification is EXPECTED[failpoint]
    if failpoint == "changeset_approval":
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
        assert not (workspace / "extra.txt").exists()
        assert "resume" in report.allowed_actions
        resumed = tuple(second.handle(ResumeRun(run_id=run_id)))
        assert any(event.type == "approval.required" for event in resumed)
        assert second.adapter.requests == []
    elif failpoint == "apply_file":
        states = {item.path: item.state.value for item in report.evidence}
        assert "before" in states.values() and "after" in states.values()
        assert "restore" in report.allowed_actions
    elif failpoint == "verification_started":
        assert report.allowed_actions == ("inspect",)
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == "new-hello\n"
    elif failpoint == "changeset_applied":
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == "new-hello\n"
        assert (workspace / "extra.txt").read_text(encoding="utf-8") == "new-extra\n"
        assert "resume" in report.allowed_actions
    elif failpoint == "verification_completed":
        assert "resume" in report.allowed_actions
        resumed = tuple(second.handle(ResumeRun(run_id=run_id)))
        assert resumed[-1].type == "run.completed"
        assert second.adapter.requests == []
    elif failpoint == "checkpoint":
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
        assert "abandon" in report.allowed_actions
