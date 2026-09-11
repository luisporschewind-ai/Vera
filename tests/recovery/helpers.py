from datetime import UTC, datetime
from pathlib import Path

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.changes import ChangeSet, FileChange
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryStage
from vera.recovery.models import PersistedChangeSet, RecoverySnapshot
from vera.workspace.changeset import ABSENT_HASH, sha256_bytes


def make_file_change(
    path: str,
    *,
    operation: str = "update",
    before: bytes = b"before\n",
    after: bytes = b"after\n",
) -> tuple[FileChange, dict[str, str]]:
    before_hash = ABSENT_HASH if operation == "create" else sha256_bytes(before)
    after_hash = ABSENT_HASH if operation == "delete" else sha256_bytes(after)
    intended: dict[str, str] = {}
    if operation != "delete":
        intended[path] = PersistedChangeSet.encode_bytes(after)
    change = FileChange(
        operation=operation,  # type: ignore[arg-type]
        path=path,
        before_hash=before_hash,
        after_hash=after_hash,
        unified_diff="@@\n",
    )
    return change, intended


def make_snapshot(
    workspace: Path,
    *,
    installation_id: str = "install-1",
    files: tuple[tuple[str, str, bytes, bytes], ...] = (
        ("app.py", "update", b"before\n", b"after\n"),
    ),
    stage: RecoveryStage = RecoveryStage.AWAITING_CHANGESET_APPROVAL,
    identity: str | None = None,
    checkpoint_id: str | None = None,
    pending: bool = True,
    verification_in_flight: bool = False,
    workspace_write_started: bool = False,
    verification_index: int = 0,
) -> RecoverySnapshot:
    from vera.recovery.probe import workspace_identity

    changes: list[FileChange] = []
    intended: dict[str, str] = {}
    for path, operation, before, after in files:
        change, encoded = make_file_change(path, operation=operation, before=before, after=after)
        changes.append(change)
        intended.update(encoded)
    persisted = None
    approval = None
    if changes:
        persisted = PersistedChangeSet(
            change_set=ChangeSet(
                changeset_id="cs_1",
                run_id="run_1",
                summary="edit",
                files=tuple(changes),
                verification=(),
                content_hash="c" * 64,
            ),
            intended_content_b64=intended,
        )
        if pending:
            approval = ApprovalRequest(
                approval_id="approval_1",
                run_id="run_1",
                kind=(
                    "changeset" if stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL else "command"
                ),
                target_id="cs_1",
                target_hash="c" * 64,
                description="review",
                risk="medium",
            )
    now = datetime(2026, 9, 11, tzinfo=UTC)
    return RecoverySnapshot(
        run_id="run_1",
        workspace_root=workspace,
        workspace_identity=identity or workspace_identity(workspace, installation_id),
        command=StartRun(goal="edit", workspace_root=workspace, model_profile="fake"),
        stage=stage,
        last_event_sequence=3,
        built_changeset=persisted,
        checkpoint_id=checkpoint_id,
        pending_approval=approval,
        verification_index=verification_index,
        verification_in_flight=verification_in_flight,
        workspace_write_started=workspace_write_started,
        created_at=now,
        updated_at=now,
        vera_version="0.1.0",
    )
