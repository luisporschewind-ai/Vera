"""Shared Core workflows on Swift, Python, and TypeScript fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import (
    EDIT_MARKER,
    PROJECT_KINDS,
    allowed_python_policy,
    copy_representative_project,
    tool_registry_for,
    turns_for,
)
from vera.contracts.commands import CancelRun, ResolveApproval, ResumeRun, RollbackRun, StartRun
from vera.contracts.recovery import RecoveryStage
from vera.models.base import FakeModelAdapter
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.runtime.engine import VeraRuntime
from vera.workspace.apply import SimulatedCrash


def _original_text(workspace: Path, relative: str) -> str:
    return (workspace / relative).read_text(encoding="utf-8")


def _runtime(workspace: Path, state: Path, kind: str, scenario: str) -> VeraRuntime:
    project = copy_representative_project(kind, workspace)
    return VeraRuntime(
        FakeModelAdapter(turns_for(project, scenario)),
        tool_registry_for(workspace),
        state,
        command_policy=allowed_python_policy(),
        installation_id="install-phase5",
        artifact_prefix=state.parent / f"{state.name}-artifacts",
    )


def _start(runtime: VeraRuntime, workspace: Path) -> tuple[str, object, list]:
    events = list(
        runtime.handle(StartRun(goal="edit", workspace_root=workspace, model_profile="fake"))
    )
    approval = next((event for event in events if event.type == "approval.required"), None)
    return events[0].run_id, approval, events


def _resolve(event: object, decision: str) -> ResolveApproval:
    payload = event.payload  # type: ignore[attr-defined]
    return ResolveApproval(
        run_id=event.run_id,  # type: ignore[attr-defined]
        approval_id=str(payload["approval_id"]),
        target_hash=str(payload["target_hash"]),
        decision=decision,
    )


def _approve_until_terminal(runtime: VeraRuntime, first_approval: object) -> list:
    events = list(runtime.handle(_resolve(first_approval, "approve")))
    while True:
        approval = next(
            (event for event in reversed(events) if event.type == "approval.required"),
            None,
        )
        if approval is None:
            return events
        events = list(runtime.handle(_resolve(approval, "approve")))


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_readonly_conversation_does_not_write(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "project"
    project = copy_representative_project(kind, workspace)
    before = _original_text(workspace, project.single_path)
    runtime = VeraRuntime(
        FakeModelAdapter(turns_for(project, "readonly")),
        tool_registry_for(workspace),
        tmp_path / "state",
    )
    events = list(
        runtime.handle(StartRun(goal="explain", workspace_root=workspace, model_profile="fake"))
    )
    types = [event.type for event in events]
    assert "changeset.proposed" not in types
    assert "changeset.applied" not in types
    assert events[-1].type == "run.completed"
    assert (workspace / project.single_path).read_text(encoding="utf-8") == before


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_single_and_multi_file_edits_apply_expected_paths(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "single"
    runtime = _runtime(workspace, tmp_path / "state-single", kind, "single")
    project = copy_representative_project(kind, workspace)
    run_id, approval, events = _start(runtime, workspace)
    assert approval is not None
    proposed = next(event for event in events if event.type == "changeset.proposed")
    files = [item["path"] for item in proposed.payload["files"]]
    assert files == [project.single_path]
    follow = _approve_until_terminal(runtime, approval)
    assert follow[-1].type == "run.completed"
    assert EDIT_MARKER in (workspace / project.single_path).read_text(encoding="utf-8")
    assert not (workspace / project.extra_path).exists()
    del run_id

    workspace_multi = tmp_path / "multi"
    runtime_multi = _runtime(workspace_multi, tmp_path / "state-multi", kind, "multi")
    project_multi = copy_representative_project(kind, workspace_multi)
    _run_id, approval_multi, _events = _start(runtime_multi, workspace_multi)
    assert approval_multi is not None
    follow_multi = _approve_until_terminal(runtime_multi, approval_multi)
    assert follow_multi[-1].type == "run.completed"
    assert EDIT_MARKER in (workspace_multi / project_multi.single_path).read_text(encoding="utf-8")
    extra_text = (workspace_multi / project_multi.extra_path).read_text(encoding="utf-8")
    assert extra_text == project_multi.extra_after


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_reject_and_cancel_are_zero_write(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "reject"
    runtime = _runtime(workspace, tmp_path / "state-reject", kind, "reject")
    project = copy_representative_project(kind, workspace)
    before = _original_text(workspace, project.single_path)
    _run_id, approval, _events = _start(runtime, workspace)
    assert approval is not None
    rejected = list(runtime.handle(_resolve(approval, "reject")))
    assert rejected[-1].type == "run.cancelled"
    assert (workspace / project.single_path).read_text(encoding="utf-8") == before

    workspace_c = tmp_path / "cancel"
    runtime_c = _runtime(workspace_c, tmp_path / "state-cancel", kind, "cancel")
    before_c = _original_text(workspace_c, project.single_path)
    run_id_c, approval_c, _events = _start(runtime_c, workspace_c)
    assert approval_c is not None
    cancelled = list(runtime_c.handle(CancelRun(run_id=run_id_c)))
    assert cancelled[-1].type == "run.cancelled"
    assert (workspace_c / project.single_path).read_text(encoding="utf-8") == before_c


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_verification_success_and_failed_rollback(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "ok"
    runtime = _runtime(workspace, tmp_path / "state-ok", kind, "verify_ok")
    project = copy_representative_project(kind, workspace)
    _run_id, approval, _events = _start(runtime, workspace)
    assert approval is not None
    follow = _approve_until_terminal(runtime, approval)
    assert follow[-1].type == "run.completed"
    assert follow[-1].payload["state"] == "completed"
    assert EDIT_MARKER in (workspace / project.single_path).read_text(encoding="utf-8")

    workspace_fail = tmp_path / "fail"
    runtime_fail = _runtime(workspace_fail, tmp_path / "state-fail", kind, "verify_fail")
    project_fail = copy_representative_project(kind, workspace_fail)
    original = _original_text(workspace_fail, project_fail.single_path)
    run_id, approval_fail, _events = _start(runtime_fail, workspace_fail)
    assert approval_fail is not None
    follow_fail = _approve_until_terminal(runtime_fail, approval_fail)
    assert follow_fail[-1].type == "run.completed"
    assert follow_fail[-1].payload["state"] == "verification_failed"
    rollback = list(runtime_fail.handle(RollbackRun(run_id=run_id)))
    assert rollback[-1].type == "rollback.completed"
    assert (workspace_fail / project_fail.single_path).read_text(encoding="utf-8") == original


class _CrashOnApproval(RecoverySnapshotStore):
    def save(self, snapshot):  # type: ignore[no-untyped-def]
        super().save(snapshot)
        if snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL:
            raise SimulatedCrash("approval")


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_interrupt_then_resume_applies_once(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "resume"
    project = copy_representative_project(kind, workspace)
    state = tmp_path / "state-resume"
    first = VeraRuntime(
        FakeModelAdapter(turns_for(project, "interrupt")),
        tool_registry_for(workspace),
        state,
        snapshot_store=_CrashOnApproval(state),
        installation_id="install-phase5",
        artifact_prefix=tmp_path / "resume-artifacts",
    )
    with pytest.raises(SimulatedCrash):
        list(first.handle(StartRun(goal="edit", workspace_root=workspace, model_profile="fake")))
    run_id = next(iter(first.runs))
    del first
    second = VeraRuntime(
        FakeModelAdapter([]),
        tool_registry_for(workspace),
        state,
        installation_id="install-phase5",
        artifact_prefix=tmp_path / "resume-artifacts",
    )
    resumed = list(second.handle(ResumeRun(run_id=run_id)))
    approval = next(event for event in resumed if event.type == "approval.required")
    follow = _approve_until_terminal(second, approval)
    assert follow[-1].type == "run.completed"
    assert EDIT_MARKER in (workspace / project.single_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", PROJECT_KINDS)
def test_path_escape_and_dangerous_command_are_rejected(tmp_path: Path, kind: str) -> None:
    sentinel = tmp_path / "outside.txt"
    sentinel.write_text("guard\n", encoding="utf-8")
    workspace = tmp_path / "escape"
    runtime = _runtime(workspace, tmp_path / "state-escape", kind, "escape")
    events = list(
        runtime.handle(StartRun(goal="escape", workspace_root=workspace, model_profile="fake"))
    )
    assert "changeset.applied" not in [event.type for event in events]
    assert sentinel.read_text(encoding="utf-8") == "guard\n"

    workspace_d = tmp_path / "danger"
    runtime_d = _runtime(workspace_d, tmp_path / "state-danger", kind, "dangerous")
    events_d = list(
        runtime_d.handle(StartRun(goal="danger", workspace_root=workspace_d, model_profile="fake"))
    )
    assert "changeset.applied" not in [event.type for event in events_d]
    assert "verification.started" not in [event.type for event in events_d]
    completed = [event for event in events_d if event.type == "tool.completed"]
    assert completed
    assert completed[0].payload.get("reason_code") == "verification_artifact_isolation_unavailable"
