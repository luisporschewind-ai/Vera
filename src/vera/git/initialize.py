"""Plan and verify a Core-owned, local Git repository initialization."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from vera.contracts import ContractModel
from vera.git.discovery import GitDiscovery, GitDiscoveryError
from vera.git.models import GitRepositoryInfo, GitRepositorySnapshot
from vera.git.service import GitService, GitServiceError
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessResult, ProcessSupervisor


class GitRepositoryInitError(ValueError):
    """Stable, redacted failure from repository initialization."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class GitRepositoryInitStatus(StrEnum):
    INITIALIZED = "initialized"
    ALREADY_INITIALIZED = "already_initialized"
    REJECTED = "rejected"
    FAILED = "failed"


class GitRepositoryInitPlan(ContractModel):
    schema_version: Literal[1] = 1
    plan_id: str
    action_id: str
    run_id: str
    workspace_identity: str
    repository_root: str
    target_device: int
    target_inode: int
    initial_branch: str
    target_kind: Literal["empty_directory", "existing_non_repository_directory"]
    target_listing_hash: str
    git_executable: str
    git_executable_device: int
    git_executable_inode: int
    git_executable_digest: str
    environment_profile_hash: str
    policy_hash: str
    sandbox_grant_hash: str


class GitRepositoryInitResult(ContractModel):
    schema_version: Literal[1] = 1
    status: Literal["initialized", "already_initialized", "rejected", "failed"]
    repository_snapshot: GitRepositorySnapshot | None = None
    available_followup_tools: tuple[str, ...] = ()
    git_identity_available: bool = False
    followup_blocked_reason: str | None = None
    reason_code: str | None = None
    receipt_id: str | None = None


class GitRepositoryInitRunner(Protocol):
    """A runner that applies an OS-enforced, single-action initialization Grant."""

    def run_git_init(
        self,
        *,
        plan: GitRepositoryInitPlan,
        workspace: Path,
        empty_template: Path,
        timeout_seconds: float,
    ) -> ProcessResult: ...


_READ_AND_BRANCH_TOOLS = (
    "git_status",
    "git_diff",
    "git_log",
    "git_show",
    "git_branch_list",
    "git_branch_create",
    "git_branch_switch",
)
_BRANCH_FORBIDDEN = re.compile(r"[\x00-\x20\x7f]")


class GitRepositoryInitService:
    def __init__(
        self,
        workspace: Path,
        *,
        supervisor: ProcessSupervisor | None = None,
        environment: Mapping[str, str] | None = None,
        runner: GitRepositoryInitRunner | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.workspace_input = Path(workspace).expanduser().absolute()
        self.workspace = self.workspace_input.resolve()
        self.supervisor = supervisor or ProcessSupervisor()
        self.environment = dict(environment) if environment is not None else os.environ.copy()
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def plan(
        self,
        *,
        run_id: str,
        action_id: str,
        workspace_identity: str,
        initial_branch: str | None = None,
        policy_hash: str = "unbound",
    ) -> GitRepositoryInitPlan | GitRepositoryInitResult:
        if not run_id or not action_id or not workspace_identity:
            raise GitRepositoryInitError("git_init_invalid_request")
        branch = initial_branch or "main"
        self._validate_target()
        self._validate_branch(branch)
        existing = self._discover_optional()
        if existing is not None:
            return self.discover(workspace_identity=workspace_identity)
        target_info = self.workspace.stat()
        git = self._git_executable()
        git_info = git.stat()
        plan_id = _plan_identity(run_id, action_id, workspace_identity)
        git_digest = _file_sha256(git)
        entries = self._listing_hash()
        environment_hash = self._environment_hash()
        grant_hash = _sandbox_grant_hash(
            run_id=run_id,
            action_id=action_id,
            plan_id=plan_id,
            workspace_identity=workspace_identity,
            workspace=str(self.workspace),
            target_device=target_info.st_dev,
            target_inode=target_info.st_ino,
            listing_hash=entries,
            branch=branch,
            git=str(git),
            git_digest=git_digest,
            environment_hash=environment_hash,
            policy_hash=policy_hash,
        )
        return GitRepositoryInitPlan(
            plan_id=plan_id,
            action_id=action_id,
            run_id=run_id,
            workspace_identity=workspace_identity,
            repository_root=str(self.workspace),
            target_device=target_info.st_dev,
            target_inode=target_info.st_ino,
            initial_branch=branch,
            target_kind=(
                "empty_directory"
                if not any(self.workspace.iterdir())
                else "existing_non_repository_directory"
            ),
            target_listing_hash=entries,
            git_executable=str(git),
            git_executable_device=git_info.st_dev,
            git_executable_inode=git_info.st_ino,
            git_executable_digest=git_digest,
            environment_profile_hash=environment_hash,
            policy_hash=policy_hash,
            sandbox_grant_hash=grant_hash,
        )

    def discover(self, *, workspace_identity: str) -> GitRepositoryInitResult:
        self._validate_target()
        repository = self._discover_optional()
        if repository is None:
            raise GitRepositoryInitError("git_not_repository")
        if Path(repository.repository_root) != self.workspace:
            raise GitRepositoryInitError("git_init_nested_repository")
        snapshot = GitService(
            self.workspace,
            supervisor=self.supervisor,
            environment=self.environment,
            timeout_seconds=self.timeout_seconds,
        ).status()
        identity_available = self._identity_available()
        return GitRepositoryInitResult(
            status=GitRepositoryInitStatus.ALREADY_INITIALIZED.value,
            repository_snapshot=snapshot,
            available_followup_tools=(
                (*_READ_AND_BRANCH_TOOLS, "git_commit")
                if identity_available
                else _READ_AND_BRANCH_TOOLS
            ),
            git_identity_available=identity_available,
            followup_blocked_reason=None if identity_available else "git_identity_missing",
        )

    def execute(self, plan: GitRepositoryInitPlan, *, approved: bool) -> GitRepositoryInitResult:
        if not approved:
            raise GitRepositoryInitError("git_init_approval_required")
        self._revalidate(plan)
        if self.runner is None:
            raise GitRepositoryInitError("git_init_backend_unsupported")
        with tempfile.TemporaryDirectory(prefix="vera-git-init-template-") as directory:
            template = Path(directory)
            result = self.runner.run_git_init(
                plan=plan,
                workspace=self.workspace,
                empty_template=template,
                timeout_seconds=self.timeout_seconds,
            )
        if result.status != "exited" or result.exit_code != 0:
            code = (
                "git_init_sandbox_denied" if result.status == "error" else "git_init_process_failed"
            )
            if self._git_marker_present():
                raise GitRepositoryInitError("git_init_partial_metadata")
            raise GitRepositoryInitError(code)
        self._revalidate_workspace_identity(plan)
        try:
            service = GitService(
                self.workspace,
                supervisor=self.supervisor,
                environment=self.environment,
                timeout_seconds=self.timeout_seconds,
            )
            snapshot = service.status()
            identity_available = self._identity_available()
            if (
                snapshot.repository_root != str(self.workspace)
                or snapshot.branch != plan.initial_branch
                or not snapshot.unborn
                or snapshot.head_oid is not None
                or service._run(("ls-files", "--stage", "-z")).stdout
                or service._run(("remote",)).stdout
            ):
                raise GitRepositoryInitError("git_init_verification_failed")
        except (GitDiscoveryError, GitServiceError) as exc:
            if self._git_marker_present():
                raise GitRepositoryInitError("git_init_partial_metadata") from exc
            raise GitRepositoryInitError("git_init_verification_failed") from exc
        if self._listing_hash(exclude_git=True) != plan.target_listing_hash:
            raise GitRepositoryInitError("git_init_verification_failed")
        return GitRepositoryInitResult(
            status=GitRepositoryInitStatus.INITIALIZED.value,
            repository_snapshot=snapshot,
            available_followup_tools=(
                (*_READ_AND_BRANCH_TOOLS, "git_commit")
                if identity_available
                else _READ_AND_BRANCH_TOOLS
            ),
            git_identity_available=identity_available,
            followup_blocked_reason=None if identity_available else "git_identity_missing",
        )

    def _revalidate(self, plan: GitRepositoryInitPlan) -> None:
        if (
            plan.repository_root != str(self.workspace)
            or self._listing_hash() != plan.target_listing_hash
            or self._environment_hash() != plan.environment_profile_hash
        ):
            raise GitRepositoryInitError("git_init_plan_stale")
        self._revalidate_workspace_identity(plan)
        git = Path(plan.git_executable)
        try:
            info = git.stat()
        except OSError as exc:
            raise GitRepositoryInitError("git_init_git_unavailable") from exc
        if (info.st_dev, info.st_ino) != (plan.git_executable_device, plan.git_executable_inode):
            raise GitRepositoryInitError("git_init_plan_stale")
        if _file_sha256(git) != plan.git_executable_digest:
            raise GitRepositoryInitError("git_init_plan_stale")
        if self._discover_optional() is not None:
            raise GitRepositoryInitError("git_init_already_initialized")

    def _revalidate_workspace_identity(self, plan: GitRepositoryInitPlan) -> None:
        if self._has_symlink_component():
            raise GitRepositoryInitError("git_init_plan_stale")
        try:
            info = self.workspace_input.lstat()
        except OSError as exc:
            raise GitRepositoryInitError("git_init_target_unsafe") from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or self.workspace_input.resolve() != self.workspace
            or (info.st_dev, info.st_ino) != (plan.target_device, plan.target_inode)
        ):
            raise GitRepositoryInitError("git_init_plan_stale")

    def _validate_target(self) -> None:
        if self._has_symlink_component():
            raise GitRepositoryInitError("git_init_target_unsafe")
        try:
            info = self.workspace_input.lstat()
        except OSError as exc:
            raise GitRepositoryInitError("git_init_target_unsafe") from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or self.workspace_input.resolve() != self.workspace
        ):
            raise GitRepositoryInitError("git_init_target_unsafe")
        marker = self.workspace / ".git"
        if (marker.exists() or marker.is_symlink()) and self._discover_optional() is None:
            raise GitRepositoryInitError("git_init_target_unsafe")

    def _discover_optional(self) -> GitRepositoryInfo | None:
        try:
            repository = GitDiscovery(
                self.workspace,
                supervisor=self.supervisor,
                environment=self.environment,
                timeout_seconds=self.timeout_seconds,
            ).discover()
        except GitDiscoveryError as exc:
            if exc.code == "git_not_repository":
                return None
            raise GitRepositoryInitError(exc.code) from exc
        if Path(repository.repository_root) != self.workspace:
            raise GitRepositoryInitError("git_init_nested_repository")
        return repository

    def _git_marker_present(self) -> bool:
        marker = self.workspace / ".git"
        return marker.exists() or marker.is_symlink()

    def _has_symlink_component(self) -> bool:
        try:
            return any(
                stat.S_ISLNK(path.lstat().st_mode)
                for path in (self.workspace_input, *self.workspace_input.parents)
            )
        except OSError as exc:
            raise GitRepositoryInitError("git_init_target_unsafe") from exc

    def _identity_available(self) -> bool:
        service = GitService(
            self.workspace,
            supervisor=self.supervisor,
            environment=self.environment,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            name = service._run(("config", "--local", "--get", "user.name"))
            email = service._run(("config", "--local", "--get", "user.email"))
        except GitServiceError as exc:
            if exc.code == "git_command_failed":
                return False
            raise GitRepositoryInitError(exc.code) from exc
        return bool(name.stdout.strip() and email.stdout.strip())

    def _validate_branch(self, branch: str) -> None:
        if (
            not branch
            or branch.startswith("-")
            or _BRANCH_FORBIDDEN.search(branch)
            or ".." in branch
            or "@{" in branch
            or branch.endswith(".lock")
            or any(part.startswith(".") or part.endswith(".") for part in branch.split("/"))
        ):
            raise GitRepositoryInitError("git_init_invalid_branch")
        git = self._git_executable()
        request = ProcessRequest(
            argv=(str(git), "check-ref-format", "--branch", branch),
            cwd=self.workspace,
            env=self._git_environment(),
            timeout_seconds=self.timeout_seconds,
            max_output_bytes=4096,
        )
        result = self.supervisor.run(request)
        if result.status != "exited" or result.exit_code != 0:
            raise GitRepositoryInitError("git_init_invalid_branch")

    def _git_executable(self) -> Path:
        from shutil import which

        selected = which("git", path=self.environment.get("PATH"))
        if selected is None:
            raise GitRepositoryInitError("git_init_git_unavailable")
        path = Path(selected).resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise GitRepositoryInitError("git_init_git_unavailable")
        return path

    def _listing_hash(self, *, exclude_git: bool = False) -> str:
        values: list[tuple[str, str, int]] = []
        try:
            with os.scandir(self.workspace) as entries:
                for index, entry in enumerate(entries):
                    if index >= 10_000:
                        raise GitRepositoryInitError("git_init_target_unsafe")
                    if exclude_git and entry.name == ".git":
                        continue
                    info = entry.stat(follow_symlinks=False)
                    kind = (
                        "symlink"
                        if stat.S_ISLNK(info.st_mode)
                        else "directory"
                        if stat.S_ISDIR(info.st_mode)
                        else "file"
                        if stat.S_ISREG(info.st_mode)
                        else "special"
                    )
                    values.append((entry.name, kind, stat.S_IMODE(info.st_mode)))
        except OSError as exc:
            raise GitRepositoryInitError("git_init_target_unsafe") from exc
        encoded = json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _git_environment(self) -> dict[str, str]:
        return build_child_environment(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_CONFIG_COUNT": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
            },
            purpose="git",
            source=self.environment,
        ).values

    def _environment_hash(self) -> str:
        payload = json.dumps(self._git_environment(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def _sandbox_grant_hash(
    *,
    run_id: str,
    action_id: str,
    plan_id: str,
    workspace_identity: str,
    workspace: str,
    target_device: int,
    target_inode: int,
    listing_hash: str,
    branch: str,
    git: str,
    git_digest: str,
    environment_hash: str,
    policy_hash: str,
) -> str:
    payload = json.dumps(
        {
            "run_id": run_id,
            "action_id": action_id,
            "plan_id": plan_id,
            "workspace_identity": workspace_identity,
            "workspace": workspace,
            "target_device": target_device,
            "target_inode": target_inode,
            "listing_hash": listing_hash,
            "branch": branch,
            "git": git,
            "git_digest": git_digest,
            "environment_hash": environment_hash,
            "policy_hash": policy_hash,
            "capability": "git_repository_initialize_once",
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _plan_identity(run_id: str, action_id: str, workspace_identity: str) -> str:
    payload = f"{run_id}\0{action_id}\0{workspace_identity}".encode()
    return hashlib.sha256(payload).hexdigest()[:32]


def _file_sha256(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as exc:
        raise GitRepositoryInitError("git_init_git_unavailable") from exc
