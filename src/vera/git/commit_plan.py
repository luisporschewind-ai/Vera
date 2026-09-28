"""Contracts and planning for exact, path-scoped local Git commits."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vera.contracts import ContractModel
from vera.git.service import GitService, GitServiceError


class GitCommitPlanError(ValueError):
    """Stable failure while constructing a Git commit plan."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class GitCommitPlan(ContractModel):
    schema_version: Literal[1] = 1
    plan_id: str
    run_id: str
    changeset_or_action_ids: tuple[str, ...]
    workspace_identity: str
    repository_root: str
    workspace_prefix: str
    head_oid: str
    branch: str
    index_fingerprint: str
    operation_state: str
    paths: tuple[str, ...]
    before_hashes: dict[str, str]
    after_hashes: dict[str, str]
    staged_diff_hash: str
    commit_message_hash: str
    verification_status: str
    hook_policy: str = "existing"
    signing_policy: str = "existing"
    policy_hash: str


class GitCommitPlanBuilder:
    def __init__(self, service: GitService) -> None:
        self.service = service

    def build(
        self,
        *,
        run_id: str,
        action_ids: tuple[str, ...],
        workspace_identity: str,
        paths: tuple[str, ...],
        message: str,
        verification_status: str,
        policy_hash: str,
    ) -> GitCommitPlan:
        if not run_id or not action_ids or not workspace_identity or not policy_hash:
            raise GitCommitPlanError("git_invalid_request")
        normalized_paths = self._normalize_paths(paths)
        self._validate_message(message)
        if verification_status != "passed":
            raise GitCommitPlanError("git_verification_failed")

        snapshot = self.service.status()
        if snapshot.unborn:
            raise GitCommitPlanError("git_unborn_head")
        if snapshot.detached:
            raise GitCommitPlanError("git_detached_head")
        if not snapshot.head_oid or not snapshot.branch:
            raise GitCommitPlanError("git_unsupported_state")
        if snapshot.operation_state != "clean":
            raise GitCommitPlanError("git_unsupported_state")
        if any(entry.conflicted for entry in snapshot.entries):
            raise GitCommitPlanError("git_conflict_present")

        status_by_path = {entry.path: entry for entry in snapshot.entries}
        for path in normalized_paths:
            entry = status_by_path.get(path)
            if entry is None:
                raise GitCommitPlanError("git_no_change")
            if entry.staged not in {" ", "."}:
                raise GitCommitPlanError("git_target_already_staged")

        repository_paths = self._repository_paths(normalized_paths)
        before_hashes = {
            path: self._head_hash(repo_path)
            for path, repo_path in zip(normalized_paths, repository_paths, strict=True)
        }
        after_hashes = {
            path: self._working_hash(repo_path)
            for path, repo_path in zip(normalized_paths, repository_paths, strict=True)
        }
        return GitCommitPlan(
            plan_id=uuid4().hex,
            run_id=run_id,
            changeset_or_action_ids=action_ids,
            workspace_identity=workspace_identity,
            repository_root=self.service.repository.repository_root,
            workspace_prefix=self.service.repository.workspace_prefix,
            head_oid=snapshot.head_oid,
            branch=snapshot.branch,
            index_fingerprint=self._digest(("ls-files", "--stage", "-z")),
            operation_state=snapshot.operation_state,
            paths=normalized_paths,
            before_hashes=before_hashes,
            after_hashes=after_hashes,
            staged_diff_hash=self._digest(
                ("diff", "--cached", "--binary", "--no-color", "--no-ext-diff", "--no-textconv")
            ),
            commit_message_hash=_sha256(message.encode("utf-8")),
            verification_status=verification_status,
            policy_hash=policy_hash,
        )

    def _normalize_paths(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        if not paths:
            raise GitCommitPlanError("git_invalid_request")
        try:
            normalized = self.service._normalize_paths(paths)
        except GitServiceError as exc:
            raise GitCommitPlanError(exc.code) from exc
        if len(set(normalized)) != len(normalized):
            raise GitCommitPlanError("git_invalid_request")
        return normalized

    def _repository_paths(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        prefix = self.service.repository.workspace_prefix
        return tuple(path if prefix == "." else f"{prefix}/{path}" for path in paths)

    def _head_hash(self, path: str) -> str:
        try:
            result = self.service._run(
                ("rev-parse", "--verify", "--end-of-options", f"HEAD:{path}")
            )
        except GitServiceError as exc:
            if exc.code == "git_command_failed":
                return ""
            raise GitCommitPlanError(exc.code) from exc
        value = result.stdout.decode("ascii", errors="strict").strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
            raise GitCommitPlanError("git_invalid_output")
        return value

    def _working_hash(self, path: str) -> str:
        candidate = self.service.repository.repository_root / Path(path)
        if not candidate.is_file():
            return ""
        try:
            result = self.service._run(("hash-object", "--", path))
        except GitServiceError as exc:
            raise GitCommitPlanError(exc.code) from exc
        return result.stdout.decode("ascii", errors="strict").strip()

    def _digest(self, arguments: tuple[str, ...]) -> str:
        try:
            result = self.service._run(arguments)
        except GitServiceError as exc:
            raise GitCommitPlanError(exc.code) from exc
        return _sha256(result.stdout)

    @staticmethod
    def _validate_message(message: str) -> None:
        encoded = message.encode("utf-8")
        if not message.strip() or len(encoded) > 8192 or message.count("\n") + 1 > 100:
            raise GitCommitPlanError("git_invalid_message")
        if any(ord(char) < 32 and char not in {"\n", "\t"} for char in message):
            raise GitCommitPlanError("git_invalid_message")
        if re.search(
            r"-----BEGIN (?:OPENSSH|RSA|EC|PGP) PRIVATE KEY-----|(?:ghp_|sk-[A-Za-z0-9])", message
        ):
            raise GitCommitPlanError("git_secret_in_message")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
