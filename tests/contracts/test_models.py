from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.changes import ChangeSet, FileChange
from vera.contracts.checkpoints import CheckpointFile, CheckpointManifest
from vera.contracts.commands import CancelRun, ResolveApproval, RollbackRun, StartRun
from vera.contracts.conversation import ConversationMessage
from vera.contracts.events import EventEnvelope
from vera.contracts.verification import (
    ARTIFACT_PROFILES,
    VerificationArtifactPlan,
    VerificationCommand,
    VerificationResult,
)


def test_start_run_accepts_conversation_and_round_trips() -> None:
    command = StartRun(
        goal="continue",
        workspace_root=Path("/tmp/project"),
        model_profile="fake",
        conversation=(
            ConversationMessage(role="user", content="inspect entry"),
            ConversationMessage(role="assistant", content="The entry is app.py"),
        ),
    )

    restored = StartRun.model_validate_json(command.model_dump_json())

    assert restored == command
    assert restored.mode == "agent"


def test_legacy_start_run_defaults_to_empty_agent_conversation() -> None:
    restored = StartRun.model_validate(
        {
            "schema_version": 1,
            "goal": "inspect",
            "workspace_root": "/tmp/project",
            "model_profile": "fake",
        }
    )

    assert restored.conversation == ()
    assert restored.mode == "agent"


def test_start_run_serializes_schema_version_and_workspace(tmp_path: Path) -> None:
    command = StartRun(goal="修复问候语", workspace_root=tmp_path, model_profile="test")
    payload = command.model_dump(mode="json")
    assert payload["schema_version"] == 1
    assert payload["workspace_root"] == str(tmp_path)


def test_contracts_reject_unknown_fields(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        StartRun(goal="goal", workspace_root=tmp_path, model_profile="test", unknown=True)

    with pytest.raises(ValidationError):
        CancelRun(run_id="run_1", unknown=True)

    with pytest.raises(ValidationError):
        ResolveApproval(
            run_id="run_1",
            approval_id="approval_1",
            target_hash="hash",
            decision="approve",
            unknown=True,
        )


def test_rollback_requires_exactly_one_target() -> None:
    with pytest.raises(ValidationError):
        RollbackRun()
    with pytest.raises(ValidationError):
        RollbackRun(run_id="run_1", checkpoint_id="checkpoint_1")


def test_change_set_and_checkpoint_models_round_trip(tmp_path: Path) -> None:
    verification = VerificationCommand(argv=("pytest", "-q"), cwd=".")
    change = FileChange(
        operation="update",
        path="hello.txt",
        before_hash="before",
        after_hash="after",
        unified_diff="@@ -1 +1 @@",
    )
    changes = ChangeSet(
        changeset_id="changeset_1",
        run_id="run_1",
        summary="更新问候语",
        files=(change,),
        verification=(verification,),
        content_hash="content_hash",
    )
    checkpoint = CheckpointManifest(
        checkpoint_id="checkpoint_1",
        run_id="run_1",
        workspace_root=tmp_path,
        before={"hello.txt": CheckpointFile(existed=True, content_hash="before", mode=0o644)},
        after_hashes={"hello.txt": "after"},
    )
    assert ChangeSet.model_validate_json(changes.model_dump_json()) == changes
    assert CheckpointManifest.model_validate_json(checkpoint.model_dump_json()) == checkpoint


def test_approval_and_verification_models_have_stable_fields(tmp_path: Path) -> None:
    approval = ApprovalRequest(
        approval_id="approval_1",
        run_id="run_1",
        kind="changeset",
        target_id="changeset_1",
        target_hash="hash",
        description="review diff",
        risk="medium",
    )
    result = VerificationResult(
        argv=("pytest", "-q"),
        cwd=str(tmp_path),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        duration_seconds=0.1,
        exit_code=0,
        stdout="passed",
        stderr="",
        status="passed",
    )
    assert approval.model_dump(mode="json")["kind"] == "changeset"
    assert result.status == "passed"


def test_event_round_trip_and_sequence_validation(tmp_path: Path) -> None:
    event = EventEnvelope(
        event_id="event_1",
        run_id="run_1",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="run.started",
        payload={"workspace_root": str(tmp_path)},
    )
    assert EventEnvelope.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_id="event_0",
            run_id="run_1",
            sequence=0,
            timestamp=datetime.now(UTC),
            type="run.started",
            payload={},
        )


@pytest.mark.parametrize("profile", ARTIFACT_PROFILES)
def test_artifact_plan_serializes_legal_profiles(profile: str) -> None:
    plan = VerificationArtifactPlan(
        profile=profile,  # type: ignore[arg-type]
        root="/private/tmp/vera-verification/abc123def456/run_1/000",
    )
    restored = VerificationArtifactPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    assert restored.schema_version == 1
    assert restored.cleanup == "always"


def test_artifact_plan_rejects_relative_root_cleanup_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        VerificationArtifactPlan(profile="pytest", root="relative/root")
    with pytest.raises(ValidationError):
        VerificationArtifactPlan(profile="pytest", cleanup="never")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        VerificationArtifactPlan.model_validate(
            {
                "schema_version": 1,
                "profile": "pytest",
                "root": "/private/tmp/vera-verification/abc/run/000",
                "cleanup": "always",
                "extra": True,
            }
        )


def test_legacy_verification_command_defaults_artifact_plan_to_none() -> None:
    restored = VerificationCommand.model_validate({"argv": ["pytest", "-q"], "cwd": "."})
    assert restored.artifact_plan is None
    command = VerificationCommand(argv=("pytest", "-q"), cwd=".")
    assert "artifact_plan" in command.model_dump(mode="json")
    assert command.model_dump(mode="json")["artifact_plan"] is None
