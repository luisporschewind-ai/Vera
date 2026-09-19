"""Read-only planning for exact, recoverable file mutations."""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vera.contracts.file_mutations import FileMutationPlan
from vera.persistence.operation_receipt import (
    OperationReceipt,
    OperationReceiptStore,
    receipt_key,
)
from vera.workspace.apply import AtomicFileWriter, FileWriter
from vera.workspace.changeset import ABSENT_HASH
from vera.workspace.checkpoint import FileMutationCheckpointStore
from vera.workspace.paths import PathFact, WorkspaceBoundaryError, WorkspacePaths


class FileMutationPlanningError(ValueError):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class PlannedFileMutation:
    plan: FileMutationPlan
    path_fact: PathFact
    before_bytes: bytes
    after_bytes: bytes


class FileMutationStatus(StrEnum):
    APPLIED = "applied"
    STALE = "stale"
    RESTORED_AFTER_FAILURE = "restored_after_failure"
    RECOVERY_REQUIRED = "recovery_required"
    ROLLED_BACK = "rolled_back"
    CONFLICTED = "conflicted"


class FileMutationRecoveryStatus(StrEnum):
    RETRY = "retry"
    COMPLETED = "completed"
    MANUAL_REQUIRED = "manual_required"


@dataclass(frozen=True)
class FileMutationResult:
    status: FileMutationStatus
    path: str
    error_code: str | None = None


@dataclass(frozen=True)
class FileMutationRecoveryResult:
    status: FileMutationRecoveryStatus
    path: str


class FileMutationPlanner:
    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths

    def plan_write(
        self,
        run_id: str,
        path: str,
        content: str,
        *,
        expected_before_hash: str | None = None,
    ) -> PlannedFileMutation:
        fact = self._inspect(path)
        target = self._target(fact)
        self._require_parent(target)
        if fact.exists and fact.kind != "regular":
            raise FileMutationPlanningError("not_regular_file")
        before = self._read_text_bytes(target, fact)
        before_hash = ABSENT_HASH if not fact.exists else _sha256(before)
        self._check_expected(before_hash, expected_before_hash)
        after = content.encode("utf-8")
        operation: Literal["create", "replace"] = "replace" if fact.exists else "create"
        return self._planned(run_id, operation, path, fact, before, after)

    def plan_edit(
        self,
        run_id: str,
        path: str,
        old_text: str,
        new_text: str,
        *,
        expected_before_hash: str | None = None,
    ) -> PlannedFileMutation:
        if not old_text:
            raise FileMutationPlanningError("empty_old_text")
        fact = self._inspect(path)
        target = self._target(fact)
        if not fact.exists:
            raise FileMutationPlanningError("not_found")
        if fact.kind != "regular":
            raise FileMutationPlanningError("not_regular_file")
        before = self._read_text_bytes(target, fact)
        before_hash = _sha256(before)
        self._check_expected(before_hash, expected_before_hash)
        try:
            text = before.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FileMutationPlanningError("non_utf8") from exc
        matches = text.count(old_text)
        if matches == 0:
            raise FileMutationPlanningError("edit_not_found")
        if matches != 1:
            raise FileMutationPlanningError("edit_not_unique")
        after = text.replace(old_text, new_text, 1).encode("utf-8")
        return self._planned(run_id, "edit", path, fact, before, after)

    def _inspect(self, path: str) -> PathFact:
        try:
            return self.paths.inspect_mutation(path)
        except WorkspaceBoundaryError as exc:
            raise FileMutationPlanningError(exc.code, str(exc)) from exc

    @staticmethod
    def _target(fact: PathFact) -> Path:
        return Path(fact.canonical_path)

    @staticmethod
    def _require_parent(target: Path) -> None:
        if not target.parent.is_dir():
            raise FileMutationPlanningError("parent_missing")

    @staticmethod
    def _read_text_bytes(target: Path, fact: PathFact) -> bytes:
        if not fact.exists:
            return b""
        try:
            data = target.read_bytes()
            data.decode("utf-8")
            return data
        except UnicodeDecodeError as exc:
            raise FileMutationPlanningError("non_utf8") from exc
        except OSError as exc:
            raise FileMutationPlanningError("read_failed", str(exc)) from exc

    @staticmethod
    def _check_expected(actual: str, expected: str | None) -> None:
        if expected is not None and expected != actual:
            raise FileMutationPlanningError("before_hash_mismatch")

    @staticmethod
    def _planned(
        run_id: str,
        operation: Literal["create", "replace", "edit"],
        path: str,
        fact: PathFact,
        before: bytes,
        after: bytes,
    ) -> PlannedFileMutation:
        before_hash = ABSENT_HASH if not fact.exists else _sha256(before)
        after_hash = _sha256(after)
        plan = FileMutationPlan(
            action_id=f"action_{uuid4().hex}",
            run_id=run_id,
            operation=operation,
            path=fact.relative_path,
            before_hash=before_hash,
            after_hash=after_hash,
            target_facts_hash=fact.digest(),
            unified_diff=_unified_diff(fact.relative_path, before, after),
            content_hash=after_hash,
        )
        return PlannedFileMutation(plan, fact, before, after)


class FileMutationApplier:
    """Checkpoint-before-effect application and conflict-safe rollback."""

    def __init__(
        self, paths: WorkspacePaths, state_dir: Path, writer: FileWriter | None = None
    ) -> None:
        self.paths = paths
        self.checkpoints = FileMutationCheckpointStore(state_dir)
        self.receipts = OperationReceiptStore(state_dir)
        self.writer: FileWriter = writer or AtomicFileWriter()

    def apply(self, planned: PlannedFileMutation) -> FileMutationResult:
        try:
            target = self.paths.resolve_mutation(planned.plan.path)
            current = self._current_bytes(planned.plan.path)
        except WorkspaceBoundaryError as exc:
            return FileMutationResult(FileMutationStatus.STALE, planned.plan.path, exc.code)
        current_hash = ABSENT_HASH if current is None else _sha256(current)
        operation_id, input_hash = _receipt_identity(planned.plan)
        existing = self.receipts.load(planned.plan.run_id, operation_id)
        if existing is not None:
            if current_hash == planned.plan.after_hash:
                return FileMutationResult(FileMutationStatus.APPLIED, planned.plan.path)
            return FileMutationResult(
                FileMutationStatus.STALE, planned.plan.path, "receipt_replayed"
            )
        if current_hash != planned.plan.before_hash:
            return FileMutationResult(
                FileMutationStatus.STALE, planned.plan.path, "before_hash_mismatch"
            )
        try:
            self.paths.revalidate(planned.path_fact)
            self.checkpoints.create(
                planned.plan,
                b"" if current is None else current,
                planned.path_fact.mode,
                workspace_root=self.paths.root,
            )
            self.writer.replace(target, planned.after_bytes, planned.path_fact.mode)
            self.receipts.save(
                OperationReceipt(
                    operation_id=operation_id,
                    operation="file_mutation",
                    run_id=planned.plan.run_id,
                    input_hash=input_hash,
                    terminal_result="file_mutation.applied",
                    effect_refs=(f"mutation:{planned.plan.action_id}",),
                    created_at=datetime.now(UTC),
                )
            )
        except Exception as exc:
            try:
                if current is None:
                    self.writer.delete(target)
                else:
                    self.writer.replace(target, current, planned.path_fact.mode)
            except Exception as restore_error:
                return FileMutationResult(
                    FileMutationStatus.RECOVERY_REQUIRED,
                    planned.plan.path,
                    f"{type(restore_error).__name__}",
                )
            return FileMutationResult(
                FileMutationStatus.RESTORED_AFTER_FAILURE,
                planned.plan.path,
                type(exc).__name__,
            )
        return FileMutationResult(FileMutationStatus.APPLIED, planned.plan.path)

    def rollback(self, plan: FileMutationPlan) -> FileMutationResult:
        checkpoint = self.checkpoints.load(plan.run_id, plan.action_id)
        try:
            target = self.paths.resolve_mutation(plan.path)
            current = self._current_bytes(plan.path)
        except WorkspaceBoundaryError as exc:
            return FileMutationResult(FileMutationStatus.CONFLICTED, plan.path, exc.code)
        current_hash = ABSENT_HASH if current is None else _sha256(current)
        if current_hash != checkpoint.after_hash:
            return FileMutationResult(FileMutationStatus.CONFLICTED, plan.path, "checksum_mismatch")
        before = self.checkpoints.before_bytes(checkpoint)
        if checkpoint.before_exists:
            self.writer.replace(target, before, checkpoint.before_mode)
        else:
            self.writer.delete(target)
        return FileMutationResult(FileMutationStatus.ROLLED_BACK, plan.path)

    def recover(
        self, plan: FileMutationPlan, *, receipt_matches: bool
    ) -> FileMutationRecoveryResult:
        try:
            current = self._current_bytes(plan.path)
        except WorkspaceBoundaryError:
            return FileMutationRecoveryResult(FileMutationRecoveryStatus.MANUAL_REQUIRED, plan.path)
        current_hash = ABSENT_HASH if current is None else _sha256(current)
        if current_hash == plan.before_hash:
            return FileMutationRecoveryResult(FileMutationRecoveryStatus.RETRY, plan.path)
        if current_hash == plan.after_hash and receipt_matches:
            return FileMutationRecoveryResult(FileMutationRecoveryStatus.COMPLETED, plan.path)
        return FileMutationRecoveryResult(FileMutationRecoveryStatus.MANUAL_REQUIRED, plan.path)

    def _current_bytes(self, path: str) -> bytes | None:
        fact = self.paths.inspect_mutation(path)
        if not fact.exists:
            return None
        return Path(fact.canonical_path).read_bytes()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _receipt_identity(plan: FileMutationPlan) -> tuple[str, str]:
    return receipt_key(
        "file_mutation",
        {
            "action_id": plan.action_id,
            "run_id": plan.run_id,
            "path": plan.path,
            "before_hash": plan.before_hash,
            "after_hash": plan.after_hash,
            "content_hash": plan.content_hash,
        },
    )


def _unified_diff(path: str, before: bytes, after: bytes) -> str:
    try:
        before_text = before.decode("utf-8")
        after_text = after.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileMutationPlanningError("non_utf8") from exc
    return "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
