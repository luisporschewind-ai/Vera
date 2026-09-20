"""Exact local branch create and switch plans."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from vera.contracts import ContractModel
from vera.git.service import GitService, GitServiceError
from vera.persistence.operation_receipt import OperationReceipt, OperationReceiptStore, receipt_key


class GitBranchError(ValueError):
    """Stable failure while planning or executing a branch operation."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class GitBranchPlan(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str
    action_id: str
    operation: Literal["create", "switch"]
    branch_name: str
    expected_head_oid: str
    expected_branch: str
    expected_worktree_hash: str
    policy_hash: str


class GitBranchResult(ContractModel):
    schema_version: Literal[1] = 1
    plan_id: str
    operation: Literal["create", "switch"]
    branch_name: str
    old_branch: str
    new_branch: str
    old_head_oid: str
    new_head_oid: str


class GitBranchPlanBuilder:
    def __init__(self, service: GitService) -> None:
        self.service = service

    def build(
        self,
        *,
        run_id: str,
        action_id: str,
        operation: Literal["create", "switch"],
        branch_name: str,
        policy_hash: str,
    ) -> GitBranchPlan:
        if not run_id or not action_id or not policy_hash:
            raise GitBranchError("git_invalid_request")
        self._validate_branch_name(branch_name)
        snapshot = self.service.status()
        if snapshot.unborn:
            raise GitBranchError("git_unborn_head")
        if snapshot.detached:
            raise GitBranchError("git_detached_head")
        if not snapshot.head_oid or not snapshot.branch:
            raise GitBranchError("git_unsupported_state")
        if snapshot.operation_state != "clean":
            raise GitBranchError("git_unsupported_state")
        if any(entry.conflicted for entry in snapshot.entries):
            raise GitBranchError("git_conflict_present")
        if snapshot.entries:
            raise GitBranchError("git_branch_dirty")
        exists = self._branch_exists(branch_name)
        if operation == "create" and exists:
            raise GitBranchError("git_branch_exists")
        if operation == "switch" and not exists:
            raise GitBranchError("git_branch_missing")
        if operation == "switch" and branch_name == snapshot.branch:
            raise GitBranchError("git_branch_already_current")
        return GitBranchPlan(
            run_id=run_id,
            action_id=action_id,
            operation=operation,
            branch_name=branch_name,
            expected_head_oid=snapshot.head_oid,
            expected_branch=snapshot.branch,
            expected_worktree_hash=self._worktree_hash(),
            policy_hash=policy_hash,
        )

    def _branch_exists(self, branch_name: str) -> bool:
        try:
            self.service._run(("show-ref", "--verify", f"refs/heads/{branch_name}"))
        except GitServiceError as exc:
            if exc.code == "git_command_failed":
                return False
            raise GitBranchError(exc.code) from exc
        return True

    def _worktree_hash(self) -> str:
        try:
            result = self.service._run(
                (
                    "status",
                    "--porcelain=v2",
                    "-z",
                    "--untracked-files=all",
                    *self.service._pathspec_args(()),
                )
            )
        except GitServiceError as exc:
            raise GitBranchError(exc.code) from exc
        return hashlib.sha256(result.stdout).hexdigest()

    def _validate_branch_name(self, branch_name: str) -> None:
        if (
            not branch_name
            or branch_name.startswith("-")
            or "\x00" in branch_name
            or any(ord(char) < 32 for char in branch_name)
        ):
            raise GitBranchError("git_invalid_branch_name")
        if not re.fullmatch(r"[^\s]+", branch_name):
            raise GitBranchError("git_invalid_branch_name")
        try:
            self.service._run(("check-ref-format", "--branch", branch_name))
        except GitServiceError as exc:
            if exc.code == "git_command_failed":
                raise GitBranchError("git_invalid_branch_name") from exc
            raise GitBranchError(exc.code) from exc


class GitBrancher:
    def __init__(self, service: GitService, *, state_dir: Path) -> None:
        self.service = service
        self.state_dir = Path(state_dir)
        self.receipts = OperationReceiptStore(self.state_dir)

    def execute(self, plan: GitBranchPlan) -> GitBranchResult:
        self._revalidate(plan)
        snapshot = self.service.status()
        old_branch = snapshot.branch
        old_head = snapshot.head_oid
        assert old_branch is not None and old_head is not None
        try:
            arguments = (
                ("branch", "--", plan.branch_name)
                if plan.operation == "create"
                else ("switch", "--", plan.branch_name)
            )
            self.service._run(arguments)
        except GitServiceError as exc:
            raise GitBranchError(
                "git_branch_failed" if exc.code == "git_command_failed" else exc.code
            ) from exc
        verified = self.service.status()
        if not verified.head_oid or verified.branch != (
            plan.branch_name if plan.operation == "switch" else old_branch
        ):
            raise GitBranchError("git_branch_result_mismatch")
        if plan.operation == "create":
            try:
                created_head = (
                    self.service._run(("rev-parse", "--verify", f"refs/heads/{plan.branch_name}"))
                    .stdout.decode("ascii", errors="strict")
                    .strip()
                )
            except GitServiceError as exc:
                raise GitBranchError("git_branch_result_mismatch") from exc
            if created_head != old_head:
                raise GitBranchError("git_branch_result_mismatch")
        result = GitBranchResult(
            plan_id=plan.action_id,
            operation=plan.operation,
            branch_name=plan.branch_name,
            old_branch=old_branch,
            new_branch=verified.branch,
            old_head_oid=old_head,
            new_head_oid=verified.head_oid,
        )
        operation_id, input_hash = receipt_key(
            "git_branch",
            {
                "action_id": plan.action_id,
                "branch_name": plan.branch_name,
                "operation": plan.operation,
                "expected_head_oid": plan.expected_head_oid,
            },
        )
        self.receipts.save(
            OperationReceipt(
                operation_id=operation_id,
                operation="git_branch",
                run_id=plan.run_id,
                input_hash=input_hash,
                terminal_result="git.branch.completed",
                effect_refs=(f"git:head:{verified.head_oid}", f"git:branch:{verified.branch}"),
                created_at=datetime.now(UTC),
            )
        )
        return result

    def _revalidate(self, plan: GitBranchPlan) -> None:
        snapshot = self.service.status()
        if snapshot.head_oid != plan.expected_head_oid or snapshot.branch != plan.expected_branch:
            raise GitBranchError("git_branch_stale")
        if snapshot.detached or snapshot.unborn or snapshot.operation_state != "clean":
            raise GitBranchError("git_unsupported_state")
        if snapshot.entries:
            raise GitBranchError("git_branch_dirty")
        builder = GitBranchPlanBuilder(self.service)
        if builder._worktree_hash() != plan.expected_worktree_hash:
            raise GitBranchError("git_branch_stale")
        exists = builder._branch_exists(plan.branch_name)
        if plan.operation == "create" and exists:
            raise GitBranchError("git_branch_exists")
        if plan.operation == "switch" and not exists:
            raise GitBranchError("git_branch_missing")
