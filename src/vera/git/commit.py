"""Exact, local, path-scoped Git commit transactions."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from vera.contracts import ContractModel
from vera.git.commit_plan import GitCommitPlan, GitCommitPlanBuilder, GitCommitPlanError
from vera.git.hooks import GitHookInspector
from vera.git.service import GitService, GitServiceError
from vera.persistence.operation_receipt import OperationReceipt, OperationReceiptStore, receipt_key
from vera.recovery.git import classify_commit_recovery


class GitCommitTransactionError(ValueError):
    """Stable failure while validating or executing a Git commit plan."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class GitCommitResult(ContractModel):
    schema_version: Literal[1] = 1
    plan_id: str
    old_head_oid: str
    new_head_oid: str
    tree_oid: str
    committed_paths: tuple[str, ...]
    remaining_staged_diff_hash: str


class GitCommitter:
    def __init__(self, service: GitService, *, state_dir: Path) -> None:
        self.service = service
        self.state_dir = Path(state_dir)
        self.receipts = OperationReceiptStore(self.state_dir)

    def execute(self, plan: GitCommitPlan, message: str) -> GitCommitResult:
        try:
            GitCommitPlanBuilder._validate_message(message)
        except GitCommitPlanError as exc:
            raise GitCommitTransactionError(exc.code) from exc
        if _sha256(message.encode("utf-8")) != plan.commit_message_hash:
            raise GitCommitTransactionError("git_plan_stale")
        operation_id, _input_hash = self._receipt_identity(plan)
        existing = self.receipts.load(plan.run_id, operation_id)
        if existing is not None:
            try:
                return self._verify_result(plan, self.service.status().entries)
            except GitCommitTransactionError as exc:
                raise GitCommitTransactionError("manual_required") from exc
        current = self.service.status()
        if current.head_oid != plan.head_oid:
            try:
                recovered = self._verify_result(plan, current.entries)
            except GitCommitTransactionError as exc:
                decision = classify_commit_recovery(
                    plan_id=plan.plan_id,
                    current_head=current.head_oid,
                    expected_head=plan.head_oid,
                    result_proven=False,
                )
                raise GitCommitTransactionError(decision.state) from exc
            decision = classify_commit_recovery(
                plan_id=plan.plan_id,
                current_head=current.head_oid,
                expected_head=plan.head_oid,
                result_proven=True,
            )
            if decision.state != "recovered":
                raise GitCommitTransactionError(decision.state)
            self._save_receipt(plan, recovered, terminal_result="git.commit.recovered")
            return recovered
        self._revalidate(plan)
        before_entries = self.service.status().entries
        self._require_identity()
        repository_paths = self._repository_paths(plan.paths)
        message_path = self._write_message(message)
        index_backup = self._backup_index(plan)
        try:
            self.service._run(("add", "-A", "--", *repository_paths))
            self.service._run(
                ("commit", "--only", "-F", str(message_path), "--", *repository_paths)
            )
        except GitServiceError as exc:
            try:
                self._restore_index(index_backup)
            except OSError as restore_exc:
                raise GitCommitTransactionError("manual_required") from restore_exc
            if self._scope_changed(before_entries, plan.paths):
                raise GitCommitTransactionError("git_hook_changed_scope") from exc
            if (
                _looks_like_signing_failure(exc)
                and GitHookInspector(self.service).signing_facts().configured
            ):
                raise GitCommitTransactionError("git_signing_unavailable") from exc
            raise GitCommitTransactionError(
                "git_commit_failed" if exc.code == "git_command_failed" else exc.code
            ) from exc
        finally:
            message_path.unlink(missing_ok=True)
        index_backup.path.unlink(missing_ok=True)
        result = self._verify_result(plan, before_entries)
        self._save_receipt(plan, result, terminal_result="git.commit.completed")
        return result

    @staticmethod
    def _receipt_identity(plan: GitCommitPlan) -> tuple[str, str]:
        return receipt_key(
            "git_commit", {"plan_id": plan.plan_id, "message_hash": plan.commit_message_hash}
        )

    def _save_receipt(
        self, plan: GitCommitPlan, result: GitCommitResult, *, terminal_result: str
    ) -> None:
        operation_id, input_hash = self._receipt_identity(plan)
        self.receipts.save(
            OperationReceipt(
                operation_id=operation_id,
                operation="git_commit",
                run_id=plan.run_id,
                input_hash=input_hash,
                terminal_result=terminal_result,
                effect_refs=(f"git:head:{result.new_head_oid}", f"git:tree:{result.tree_oid}"),
                facts={
                    "plan_id": result.plan_id,
                    "old_head_oid": result.old_head_oid,
                    "new_head_oid": result.new_head_oid,
                    "tree_oid": result.tree_oid,
                    "committed_paths": "\0".join(result.committed_paths),
                    "remaining_staged_diff_hash": result.remaining_staged_diff_hash,
                },
                created_at=datetime.now(UTC),
            )
        )

    def _revalidate(self, plan: GitCommitPlan) -> None:
        snapshot = self.service.status()
        if snapshot.head_oid != plan.head_oid:
            raise GitCommitTransactionError("git_head_changed")
        if snapshot.branch != plan.branch or snapshot.detached or snapshot.unborn:
            raise GitCommitTransactionError("git_plan_stale")
        if snapshot.operation_state != "clean":
            raise GitCommitTransactionError("git_unsupported_state")
        if any(entry.conflicted for entry in snapshot.entries):
            raise GitCommitTransactionError("git_conflict_present")
        builder = GitCommitPlanBuilder(self.service)
        if builder._digest(("ls-files", "--stage", "-z")) != plan.index_fingerprint:
            raise GitCommitTransactionError("git_index_changed")
        for path, repository_path in zip(
            plan.paths, self._repository_paths(plan.paths), strict=True
        ):
            entry = next((item for item in snapshot.entries if item.path == path), None)
            if entry is None or entry.staged not in {" ", "."}:
                raise GitCommitTransactionError("git_plan_stale")
            if builder._head_hash(repository_path) != plan.before_hashes[path]:
                raise GitCommitTransactionError("git_plan_stale")
            if builder._working_hash(repository_path) != plan.after_hashes[path]:
                raise GitCommitTransactionError("git_plan_stale")

    def _verify_result(
        self, plan: GitCommitPlan, before_entries: tuple[object, ...]
    ) -> GitCommitResult:
        try:
            new_head = (
                self.service._run(("rev-parse", "--verify", "HEAD")).stdout.decode("ascii").strip()
            )
            tree_oid = (
                self.service._run(("rev-parse", "--verify", "HEAD^{tree}"))
                .stdout.decode("ascii")
                .strip()
            )
            parent_oid = (
                self.service._run(("rev-parse", "--verify", f"{new_head}^"))
                .stdout.decode("ascii")
                .strip()
            )
            committed = self.service._run(
                ("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", new_head)
            ).stdout
        except GitServiceError as exc:
            raise GitCommitTransactionError("git_commit_result_mismatch") from exc
        if parent_oid != plan.head_oid:
            raise GitCommitTransactionError("git_commit_result_mismatch")
        builder = GitCommitPlanBuilder(self.service)
        for path, repository_path in zip(
            plan.paths, self._repository_paths(plan.paths), strict=True
        ):
            if builder._head_hash(repository_path) != plan.after_hashes[path]:
                raise GitCommitTransactionError("git_commit_result_mismatch")
            if builder._working_hash(repository_path) != plan.after_hashes[path]:
                raise GitCommitTransactionError("git_commit_result_mismatch")
        paths = tuple(
            item.decode("utf-8", errors="strict") for item in committed.split(b"\0") if item
        )
        workspace_paths = tuple(self.service._workspace_path(path) for path in paths)
        visible = tuple(path for path in workspace_paths if path is not None)
        if set(visible) != set(plan.paths):
            raise GitCommitTransactionError("git_commit_result_mismatch")
        if self._scope_changed(before_entries, plan.paths):
            raise GitCommitTransactionError("git_hook_changed_scope")
        remaining = builder._digest(
            ("diff", "--cached", "--binary", "--no-color", "--no-ext-diff", "--no-textconv")
        )
        if remaining != plan.staged_diff_hash:
            raise GitCommitTransactionError("git_commit_result_mismatch")
        return GitCommitResult(
            plan_id=plan.plan_id,
            old_head_oid=plan.head_oid,
            new_head_oid=new_head,
            tree_oid=tree_oid,
            committed_paths=plan.paths,
            remaining_staged_diff_hash=remaining,
        )

    def _scope_changed(self, before_entries: tuple[object, ...], paths: tuple[str, ...]) -> bool:
        ignored = set(paths)
        before = {
            self._entry_key(entry)
            for entry in before_entries
            if getattr(entry, "path", None) not in ignored
            and getattr(entry, "original_path", None) not in ignored
        }
        after_snapshot = self.service.status()
        after = {
            self._entry_key(entry)
            for entry in after_snapshot.entries
            if entry.path not in ignored and entry.original_path not in ignored
        }
        return before != after

    @staticmethod
    def _entry_key(entry: object) -> tuple[object, ...]:
        return (
            getattr(entry, "path", None),
            getattr(entry, "original_path", None),
            getattr(entry, "staged", None),
            getattr(entry, "unstaged", None),
            getattr(entry, "untracked", None),
            getattr(entry, "ignored", None),
            getattr(entry, "conflicted", None),
            getattr(entry, "submodule", None),
        )

    def _require_identity(self) -> None:
        try:
            result = self.service._run(("var", "GIT_COMMITTER_IDENT"))
        except GitServiceError as exc:
            if exc.code == "git_command_failed":
                raise GitCommitTransactionError("git_identity_missing") from exc
            raise GitCommitTransactionError(exc.code) from exc
        if not result.stdout.decode("utf-8", errors="replace").strip():
            raise GitCommitTransactionError("git_identity_missing")

    def _repository_paths(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        prefix = self.service.repository.workspace_prefix
        return tuple(path if prefix == "." else f"{prefix}/{path}" for path in paths)

    def _write_message(self, message: str) -> Path:
        directory = self.state_dir / "git-commit"
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        fd, raw_path = tempfile.mkstemp(prefix="message-", suffix=".txt", dir=directory)
        path = Path(raw_path)
        os.chmod(path, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(message)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    def _backup_index(self, plan: GitCommitPlan) -> _IndexBackup:
        try:
            index_path = self._index_path()
            mode = index_path.stat().st_mode & 0o777
            directory = self.state_dir / "git-commit"
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
            backup_path = directory / f"index-{plan.plan_id}.bak"
            backup_path.write_bytes(index_path.read_bytes())
            os.chmod(backup_path, 0o600)
            return _IndexBackup(path=backup_path, index_path=index_path, mode=mode)
        except (OSError, GitServiceError) as exc:
            raise GitCommitTransactionError("git_index_backup_failed") from exc

    def _restore_index(self, backup: _IndexBackup) -> None:
        temporary = backup.path.with_suffix(".restore")
        try:
            temporary.write_bytes(backup.path.read_bytes())
            os.chmod(temporary, backup.mode)
            os.replace(temporary, backup.index_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _index_path(self) -> Path:
        result = self.service._run(("rev-parse", "--git-path", "index"))
        raw = result.stdout.decode("utf-8", errors="strict").strip()
        path = Path(raw)
        return path if path.is_absolute() else self.service.repository.repository_root / path


@dataclass(frozen=True)
class _IndexBackup:
    path: Path
    index_path: Path
    mode: int


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _looks_like_signing_failure(exc: GitServiceError) -> bool:
    diagnostic = exc.stderr.decode("utf-8", errors="replace").casefold()
    return any(
        marker in diagnostic
        for marker in ("gpg failed", "signing failed", "could not load public key", "ssh-keygen")
    )
