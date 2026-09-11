from __future__ import annotations

import sys
from pathlib import Path

from vera.contracts.commands import ResolveApproval, StartRun
from vera.contracts.recovery import RecoveryStage
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.runtime.engine import VeraRuntime
from vera.tools.command_policy import CommandPolicy
from vera.tools.registry import ToolRegistry


def _proposal(verification: list[dict[str, object]] | None = None) -> ModelTurn:
    arguments: dict[str, object] = {
        "summary": "edit",
        "changes": [
            {
                "operation": "update",
                "path": "hello.txt",
                "after_content": "new\n",
            }
        ],
    }
    if verification is not None:
        arguments["verification"] = verification
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(ModelToolCall(call_id="1", name="propose_changeset", arguments=arguments),),
    )


def make_runtime(
    tmp_path: Path,
    turns: list[ModelTurn],
    *,
    snapshot_store: RecoverySnapshotStore | None = None,
    command_policy: CommandPolicy | None = None,
) -> tuple[VeraRuntime, RecoverySnapshotStore]:
    store = snapshot_store or RecoverySnapshotStore(tmp_path / "state")
    runtime = VeraRuntime(
        FakeModelAdapter(turns),
        ToolRegistry(),
        tmp_path / "state",
        command_policy=command_policy,
        snapshot_store=store,
        installation_id="install-1",
    )
    return runtime, store


def resolve(event, decision: str = "approve") -> ResolveApproval:
    return ResolveApproval(
        run_id=event.run_id,
        approval_id=str(event.payload["approval_id"]),
        target_hash=str(event.payload["target_hash"]),
        decision=decision,
    )


def test_changeset_approval_snapshot_references_required_event(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime, store = make_runtime(tmp_path, [_proposal()])
    events = tuple(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    snapshot = store.load(events[0].run_id)

    assert snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL
    assert snapshot.last_event_sequence == events[-1].sequence
    assert events[-1].type == "approval.required"
    assert snapshot.pending_approval is not None
    assert snapshot.built_changeset is not None


def test_started_and_terminal_snapshots(tmp_path: Path) -> None:
    runtime, store = make_runtime(
        tmp_path,
        [ModelTurn(assistant_text="hello", finish_reason="stop")],
    )
    events = list(
        runtime.handle(StartRun(goal="Hello", workspace_root=tmp_path, model_profile="fake"))
    )
    snapshot = store.load(events[0].run_id)
    assert snapshot.stage is RecoveryStage.TERMINAL
    assert snapshot.last_event_sequence == events[-1].sequence
    assert events[-1].type == "run.completed"
    assert snapshot.workspace_write_started is False


def test_checkpoint_apply_and_verification_snapshots(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    policy = CommandPolicy(user_allowed_prefixes=((sys.executable, "-c"),))
    runtime, store = make_runtime(
        tmp_path,
        [
            _proposal(
                [
                    {
                        "argv": [sys.executable, "-c", "print('ok')"],
                        "cwd": ".",
                    }
                ]
            )
        ],
        command_policy=policy,
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    follow_up = list(runtime.handle(resolve(approval)))
    snapshot = store.load(start_events[0].run_id)

    assert [event.type for event in follow_up] == [
        "approval.resolved",
        "checkpoint.created",
        "changeset.applied",
        "verification.started",
        "verification.completed",
        "run.completed",
    ]
    assert snapshot.stage is RecoveryStage.TERMINAL
    assert snapshot.workspace_write_started is True
    assert snapshot.checkpoint_id is not None
    assert snapshot.verification_in_flight is False
    assert snapshot.last_event_sequence == follow_up[-1].sequence


def test_verification_started_snapshot_marks_in_flight(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    policy = CommandPolicy(user_allowed_prefixes=((sys.executable, "-c"),))
    stages: list[RecoveryStage] = []
    in_flight: list[bool] = []

    class RecordingStore(RecoverySnapshotStore):
        def save(self, snapshot):  # type: ignore[no-untyped-def]
            stages.append(snapshot.stage)
            in_flight.append(snapshot.verification_in_flight)
            super().save(snapshot)

    runtime, _store = make_runtime(
        tmp_path,
        [_proposal([{"argv": [sys.executable, "-c", "print('ok')"], "cwd": "."}])],
        snapshot_store=RecordingStore(tmp_path / "state"),
        command_policy=policy,
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    list(runtime.handle(resolve(approval)))

    assert RecoveryStage.VERIFYING in stages
    assert True in in_flight
    assert in_flight[-1] is False


def test_verification_approval_snapshot(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    runtime, store = make_runtime(
        tmp_path,
        [_proposal([{"argv": ["ruff", "check", "."], "cwd": "."}])],
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    follow_up = list(runtime.handle(resolve(approval)))
    command_approval = next(event for event in follow_up if event.type == "approval.required")
    snapshot = store.load(start_events[0].run_id)

    assert snapshot.stage is RecoveryStage.AWAITING_VERIFICATION_APPROVAL
    assert snapshot.last_event_sequence == command_approval.sequence
    assert snapshot.pending_approval is not None
    assert snapshot.workspace_write_started is True


def test_snapshot_write_failure_does_not_enter_next_side_effect(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    target = tmp_path / "hello.txt"

    class FailOnApproval(RecoverySnapshotStore):
        def save(self, snapshot):  # type: ignore[no-untyped-def]
            if snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL:
                raise RecoverySnapshotError("snapshot_write_failed")
            super().save(snapshot)

    runtime, store = make_runtime(
        tmp_path,
        [_proposal()],
        snapshot_store=FailOnApproval(tmp_path / "state"),
    )
    adapter = runtime.adapter
    assert isinstance(adapter, FakeModelAdapter)
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )

    assert events[-1].type == "run.failed"
    assert events[-1].payload["reason"] == "snapshot_write_failed"
    assert not any(event.type == "approval.required" for event in events)
    assert target.read_text(encoding="utf-8") == "old\n"
    started = store.load(events[-1].run_id)
    assert started.stage is RecoveryStage.STARTED


def test_checkpoint_snapshot_failure_does_not_apply(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")

    class FailOnCheckpoint(RecoverySnapshotStore):
        def save(self, snapshot):  # type: ignore[no-untyped-def]
            if snapshot.stage is RecoveryStage.CHECKPOINT_READY:
                raise RecoverySnapshotError("snapshot_write_failed")
            super().save(snapshot)

    runtime, _store = make_runtime(
        tmp_path,
        [_proposal()],
        snapshot_store=FailOnCheckpoint(tmp_path / "state"),
    )
    start_events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    approval = next(event for event in start_events if event.type == "approval.required")
    follow_up = list(runtime.handle(resolve(approval)))

    assert follow_up[-1].type == "run.failed"
    assert follow_up[-1].payload["reason"] == "snapshot_write_failed"
    assert not any(event.type == "changeset.applied" for event in follow_up)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old\n"


def test_compaction_run_does_not_write_snapshot(tmp_path: Path) -> None:
    runtime, store = make_runtime(
        tmp_path,
        [ModelTurn(assistant_text="summary", finish_reason="stop")],
    )
    events = list(
        runtime.handle(
            StartRun(
                goal="summarize",
                workspace_root=tmp_path,
                model_profile="fake",
                mode="compact",
            )
        )
    )
    assert events[-1].type == "run.completed"
    assert store.exists(events[0].run_id) is False
