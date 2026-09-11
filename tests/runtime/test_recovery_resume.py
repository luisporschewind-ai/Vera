from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vera.contracts.commands import ResolveApproval, ResumeRun, StartRun
from vera.contracts.recovery import RecoveryStage
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.redaction import Redactor
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


def test_new_runtime_resumes_changeset_approval(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    first, store = make_runtime(tmp_path, [_proposal()])
    approval = next(
        event
        for event in first.handle(
            StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake")
        )
        if event.type == "approval.required"
    )

    second, _store = make_runtime(tmp_path, [], snapshot_store=store)
    resumed = tuple(second.handle(ResumeRun(run_id=approval.run_id)))
    pending = next(event for event in resumed if event.type == "approval.required")

    assert pending.payload["approval_id"] == approval.payload["approval_id"]
    assert any(event.type == "recovery.resume_started" for event in resumed)
    assert any(event.type == "recovery.resumed" for event in resumed)
    assert second.adapter.requests == []

    follow_up = tuple(second.handle(resolve(pending)))
    assert sum(1 for event in follow_up if event.type == "checkpoint.created") == 1
    assert any(event.type == "changeset.applied" for event in follow_up)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "new\n"


def test_resume_then_approve_creates_checkpoint_once(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    first, store = make_runtime(tmp_path, [_proposal()])
    approval = next(
        event
        for event in first.handle(
            StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    second, _store = make_runtime(tmp_path, [], snapshot_store=store)
    pending = next(
        event
        for event in second.handle(ResumeRun(run_id=approval.run_id))
        if event.type == "approval.required"
    )
    duplicate = tuple(second.handle(ResumeRun(run_id=approval.run_id)))
    follow_up = tuple(second.handle(resolve(pending)))

    journal = EventJournal(tmp_path / "state", approval.run_id, Redactor([]))
    types = [event.type for event in journal.read_all()]
    assert types.count("recovery.resume_started") == 1
    assert types.count("checkpoint.created") == 1
    assert types.count("changeset.applied") == 1
    assert not any(event.type == "changeset.applied" for event in duplicate)
    assert follow_up[-1].type == "run.completed"


def test_new_runtime_resumes_verification_index(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    first_cmd = (
        sys.executable,
        "-c",
        "from pathlib import Path; p=Path('v1.txt'); "
        "p.write_text((p.read_text() if p.exists() else '') + 'x')",
    )
    second_cmd = (
        sys.executable,
        "-c",
        "from pathlib import Path; Path('v2.txt').write_text('ok')",
    )

    class CrashAfterFirstVerification(RecoverySnapshotStore):
        def save(self, snapshot):  # type: ignore[no-untyped-def]
            super().save(snapshot)
            if (
                snapshot.stage is RecoveryStage.VERIFYING
                and snapshot.verification_index == 1
                and not snapshot.verification_in_flight
            ):
                raise RuntimeError("simulated crash")

    store = CrashAfterFirstVerification(tmp_path / "state")
    first, _store = make_runtime(
        tmp_path,
        [
            _proposal(
                [
                    {"argv": list(first_cmd), "cwd": "."},
                    {"argv": list(second_cmd), "cwd": "."},
                ]
            )
        ],
        snapshot_store=store,
        command_policy=CommandPolicy(user_allowed_prefixes=(first_cmd, second_cmd)),
    )
    approval = next(
        event
        for event in first.handle(
            StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        list(first.handle(resolve(approval)))

    assert (tmp_path / "v1.txt").read_text(encoding="utf-8") == "x"
    assert not (tmp_path / "v2.txt").exists()

    second, _again = make_runtime(
        tmp_path,
        [],
        snapshot_store=RecoverySnapshotStore(tmp_path / "state"),
        command_policy=CommandPolicy(user_allowed_prefixes=(first_cmd, second_cmd)),
    )
    resumed = tuple(second.handle(ResumeRun(run_id=approval.run_id)))

    assert second.adapter.requests == []
    assert (tmp_path / "v1.txt").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "v2.txt").read_text(encoding="utf-8") == "ok"
    assert any(event.type == "verification.completed" for event in resumed)
    assert resumed[-1].type == "run.completed"


def test_resume_verification_approval_keeps_pending_id(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    first, store = make_runtime(
        tmp_path,
        [_proposal([{"argv": ["ruff", "check", "."], "cwd": "."}])],
    )
    start_events = tuple(
        first.handle(StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake"))
    )
    changeset = next(event for event in start_events if event.type == "approval.required")
    follow_up = tuple(first.handle(resolve(changeset)))
    command_approval = next(event for event in follow_up if event.type == "approval.required")

    second, _store = make_runtime(tmp_path, [], snapshot_store=store)
    resumed = tuple(second.handle(ResumeRun(run_id=command_approval.run_id)))
    pending = next(event for event in resumed if event.type == "approval.required")
    assert pending.payload["approval_id"] == command_approval.payload["approval_id"]
    assert pending.payload["kind"] == "command"
    assert second.adapter.requests == []


def test_resume_manual_required_does_not_hydrate(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("old\n", encoding="utf-8")
    first, store = make_runtime(tmp_path, [_proposal()])
    approval = next(
        event
        for event in first.handle(
            StartRun(goal="edit", workspace_root=tmp_path, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    (tmp_path / "hello.txt").write_text("tampered\n", encoding="utf-8")
    second, _store = make_runtime(tmp_path, [], snapshot_store=store)
    events = tuple(second.handle(ResumeRun(run_id=approval.run_id)))

    assert approval.run_id not in second.runs
    assert events[-1].type in {"recovery.detected", "recovery.manual_required"}
    assert events[-1].payload["classification"] == "manual_required"
    assert any(event.type == "approval.invalidated" for event in events)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "tampered\n"


def test_resume_partial_restore_requires_approval(tmp_path: Path) -> None:
    from tests.recovery.helpers import PartialRecoveryFixture

    fixture = PartialRecoveryFixture(tmp_path)
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        fixture.state_dir,
        snapshot_store=RecoverySnapshotStore(fixture.state_dir),
        installation_id="install-1",
    )
    resumed = tuple(runtime.handle(ResumeRun(run_id="run_1")))
    pending = next(event for event in resumed if event.type == "approval.required")

    assert any(event.type == "recovery.restore_proposed" for event in resumed)
    assert pending.payload["kind"] == "recovery"
    assert fixture.after_file.read_bytes() == b"after-b\n"
    assert runtime.adapter.requests == []

    follow_up = tuple(runtime.handle(resolve(pending)))
    assert any(event.type == "recovery.restored" for event in follow_up)
    assert follow_up[-1].type == "run.completed"
    assert fixture.before_file.read_bytes() == b"before-a\n"
    assert fixture.after_file.read_bytes() == b"before-b\n"
    assert tuple(runtime.handle(resolve(pending))) == ()


def test_reject_partial_restore_does_not_write(tmp_path: Path) -> None:
    from tests.recovery.helpers import PartialRecoveryFixture

    fixture = PartialRecoveryFixture(tmp_path)
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        fixture.state_dir,
        snapshot_store=RecoverySnapshotStore(fixture.state_dir),
        installation_id="install-1",
    )
    pending = next(
        event
        for event in runtime.handle(ResumeRun(run_id="run_1"))
        if event.type == "approval.required"
    )
    follow_up = tuple(runtime.handle(resolve(pending, "reject")))
    assert follow_up[-1].type == "run.cancelled"
    assert fixture.after_file.read_bytes() == b"after-b\n"


def test_wrong_recovery_hash_is_rejected(tmp_path: Path) -> None:
    from tests.recovery.helpers import PartialRecoveryFixture

    fixture = PartialRecoveryFixture(tmp_path)
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        fixture.state_dir,
        snapshot_store=RecoverySnapshotStore(fixture.state_dir),
        installation_id="install-1",
    )
    pending = next(
        event
        for event in runtime.handle(ResumeRun(run_id="run_1"))
        if event.type == "approval.required"
    )
    events = tuple(
        runtime.handle(
            ResolveApproval(
                run_id=pending.run_id,
                approval_id=str(pending.payload["approval_id"]),
                target_hash="0" * 64,
                decision="approve",
            )
        )
    )
    assert events[-1].type == "run.failed"
    assert fixture.after_file.read_bytes() == b"after-b\n"
