"""Bounded, local-only Git read service."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath

from vera.git.discovery import GitDiscovery, GitDiscoveryError
from vera.git.models import (
    GitBranchSummary,
    GitCommitSummary,
    GitDiffRequest,
    GitDiffResult,
    GitLogRequest,
    GitRepositorySnapshot,
    GitShowRequest,
    GitShowResult,
    GitStatusEntry,
)
from vera.git.parsers import parse_status_porcelain_v2
from vera.process.environment import build_child_environment
from vera.process.supervisor import ProcessRequest, ProcessResult, ProcessSupervisor
from vera.workspace.paths import ProtectedPathPolicy


class GitServiceError(ValueError):
    """Stable, redacted error from a native Git read operation."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class GitService:
    def __init__(
        self,
        workspace: Path,
        *,
        supervisor: ProcessSupervisor | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 10.0,
        max_output_bytes: int = 100_000,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.supervisor = supervisor or ProcessSupervisor()
        self.environment = dict(environment) if environment is not None else os.environ.copy()
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max(1, max_output_bytes)
        try:
            self.repository = GitDiscovery(
                self.workspace,
                supervisor=self.supervisor,
                environment=self.environment,
                timeout_seconds=timeout_seconds,
            ).discover()
        except GitDiscoveryError as exc:
            raise GitServiceError(exc.code, str(exc)) from exc
        self.protected = ProtectedPathPolicy()

    def status(self) -> GitRepositorySnapshot:
        result = self._run(
            (
                "status",
                "--porcelain=v2",
                "-z",
                "--branch",
                "--untracked-files=all",
                *self._pathspec_args(()),
            )
        )
        try:
            parsed = parse_status_porcelain_v2(result.stdout)
        except ValueError as exc:
            raise GitServiceError("git_invalid_output", "Git status output was invalid") from exc
        entries = tuple(self._filter_status_entry(entry) for entry in parsed.entries)
        return GitRepositorySnapshot(
            repository_root=self.repository.repository_root,
            workspace_prefix=self.repository.workspace_prefix,
            head_oid=parsed.head_oid,
            branch=parsed.branch,
            detached=parsed.detached,
            unborn=parsed.unborn,
            upstream=parsed.upstream,
            ahead=parsed.ahead,
            behind=parsed.behind,
            operation_state=self._operation_state(),
            entries=tuple(entry for entry in entries if entry is not None),
        )

    def diff(self, request: GitDiffRequest) -> GitDiffResult:
        paths = self._normalize_paths(request.paths)
        pathspecs = self._pathspec_args(paths)
        scope_args = self._diff_scope_args(request)
        files_result = self._run(
            (
                "diff",
                "--no-ext-diff",
                "--no-color",
                "--no-textconv",
                "--name-only",
                "-z",
                *scope_args,
                *pathspecs,
            )
        )
        files = self._filter_paths(_nul_paths(files_result.stdout))
        patch_args = [
            "diff",
            "--no-ext-diff",
            "--no-color",
            "--no-textconv",
            f"-U{request.context_lines}",
        ]
        if request.stat_only:
            patch_args.append("--stat")
        patch_result = self._run((*patch_args, *scope_args, *pathspecs))
        binary_result = self._run(
            (
                "diff",
                "--no-ext-diff",
                "--no-color",
                "--no-textconv",
                "--numstat",
                "-z",
                *scope_args,
                *pathspecs,
            )
        )
        return GitDiffResult(
            scope=request.scope,
            patch=_decode_output(patch_result.stdout),
            files=files,
            truncated=patch_result.stdout_truncated,
            binary_files=self._binary_paths(binary_result.stdout),
        )

    def log(self, request: GitLogRequest) -> tuple[GitCommitSummary, ...]:
        paths = self._normalize_paths(request.paths)
        pathspecs = self._pathspec_args(paths)
        oid = self._resolve_ref(request.ref)
        result = self._run(
            (
                "log",
                "--no-decorate",
                "--date=iso-strict",
                "--pretty=format:%H%x00%P%x00%an%x00%aI%x00%s%x00",
                "-n",
                str(request.limit),
                oid,
                *pathspecs,
            )
        )
        fields = result.stdout.split(b"\0")
        if fields and not fields[-1]:
            fields.pop()
        if len(fields) % 5:
            raise GitServiceError("git_invalid_output", "Git log output was invalid")
        summaries: list[GitCommitSummary] = []
        for offset in range(0, len(fields), 5):
            try:
                commit_oid = _decode_field(fields[offset].strip())
                parents = tuple(_decode_field(fields[offset + 1].strip()).split())
                author_name = _decode_field(fields[offset + 2].strip())
                authored_at = datetime.fromisoformat(_decode_field(fields[offset + 3].strip()))
                subject = _decode_field(fields[offset + 4].strip())
            except (UnicodeDecodeError, ValueError) as exc:
                raise GitServiceError("git_invalid_output", "Git log output was invalid") from exc
            summaries.append(
                GitCommitSummary(
                    oid=commit_oid,
                    parent_oids=parents,
                    author_name=author_name,
                    authored_at=authored_at,
                    subject=subject,
                )
            )
        return tuple(summaries)

    def show(self, request: GitShowRequest) -> GitShowResult:
        paths = self._normalize_paths(request.paths)
        pathspecs = self._pathspec_args(paths)
        oid = self._resolve_ref(request.ref)
        commits = self.log(GitLogRequest(ref=oid, limit=1))
        if not commits:
            raise GitServiceError("git_invalid_ref", "Git ref did not resolve to a commit")
        files_result = self._run(
            (
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-r",
                "-z",
                oid,
                *pathspecs,
            )
        )
        files = self._filter_paths(_nul_paths(files_result.stdout))
        patch_result = self._run(
            (
                "show",
                "--no-ext-diff",
                "--no-color",
                "--no-textconv",
                "--format=",
                f"-U{request.context_lines}",
                oid,
                *pathspecs,
            )
        )
        binary_result = self._run(
            (
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--numstat",
                "-r",
                "-z",
                oid,
                *pathspecs,
            )
        )
        patch = _decode_output(patch_result.stdout)
        return GitShowResult(
            commit=commits[0],
            files=files,
            diff=GitDiffResult(
                scope="range",
                patch=patch,
                files=files,
                truncated=patch_result.stdout_truncated,
                binary_files=self._binary_paths(binary_result.stdout),
            ),
        )

    def branches(self) -> tuple[GitBranchSummary, ...]:
        result = self._run(
            (
                "for-each-ref",
                "--format=%(HEAD)%00%(refname:short)%00%(objectname)%00%(upstream:short)%00%(upstream:track)%00",
                "refs/heads",
            )
        )
        fields = result.stdout.split(b"\0")
        if fields and not fields[-1].strip():
            fields.pop()
        if len(fields) % 5:
            raise GitServiceError("git_invalid_output", "Git branch output was invalid")
        branches: list[GitBranchSummary] = []
        for offset in range(0, len(fields), 5):
            head = _decode_field(fields[offset].strip())
            name = _decode_field(fields[offset + 1].strip())
            oid = _decode_field(fields[offset + 2].strip())
            upstream = _decode_field(fields[offset + 3].strip()) or None
            ahead, behind = _parse_track(_decode_field(fields[offset + 4].strip()))
            branches.append(
                GitBranchSummary(
                    name=name,
                    current=head == "*",
                    oid=oid,
                    upstream=upstream,
                    ahead=ahead,
                    behind=behind,
                )
            )
        return tuple(branches)

    def _run(self, arguments: tuple[str, ...]) -> ProcessResult:
        result = self.supervisor.run(
            ProcessRequest(
                argv=("git", "-C", self.repository.repository_root, *arguments),
                cwd=self.workspace,
                env=self._environment(),
                timeout_seconds=self.timeout_seconds,
                max_output_bytes=self.max_output_bytes,
            )
        )
        if result.status != "exited":
            raise GitServiceError(
                {
                    "timed_out": "git_timeout",
                    "cancelled": "git_cancelled",
                }.get(result.status, "git_process_error")
            )
        if result.exit_code not in {0, None}:
            raise GitServiceError("git_command_failed", "Git command failed")
        return result

    def _resolve_ref(self, ref: str) -> str:
        if not ref.strip() or "\x00" in ref:
            raise GitServiceError("git_invalid_ref", "Git ref is invalid")
        result = self._run(("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"))
        oid = _decode_output(result.stdout).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", oid):
            raise GitServiceError("git_invalid_output", "Git ref output was invalid")
        return oid

    def _diff_scope_args(self, request: GitDiffRequest) -> tuple[str, ...]:
        if request.scope == "working":
            return ()
        if request.scope == "staged":
            return ("--cached",)
        if request.scope == "head":
            return ("HEAD",)
        if not request.base or not request.target:
            raise GitServiceError("git_invalid_request", "range diff requires base and target")
        return (self._resolve_ref(request.base), self._resolve_ref(request.target))

    def _normalize_paths(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in paths:
            value = raw.replace("\\", "/")
            path = PurePosixPath(value)
            if not value or path.is_absolute() or ".." in path.parts:
                raise GitServiceError("git_path_escape", "Git path must be workspace-relative")
            if self.protected.is_protected(Path(path)):
                raise GitServiceError("git_protected_path", "protected Git paths are not exposed")
            normalized.append(path.as_posix())
        return tuple(normalized)

    def _pathspec_args(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        prefix = self.repository.workspace_prefix
        if paths:
            repository_paths = tuple(
                path if prefix == "." else f"{prefix}/{path}" for path in paths
            )
        elif prefix != ".":
            repository_paths = (f"{prefix}/",)
        else:
            repository_paths = ()
        return ("--", *repository_paths) if repository_paths else ()

    def _filter_status_entry(self, entry: GitStatusEntry) -> GitStatusEntry | None:
        path = self._workspace_path(entry.path)
        original = self._workspace_path(entry.original_path) if entry.original_path else None
        if path is None or (entry.original_path is not None and original is None):
            return None
        if self.protected.is_protected(Path(path)):
            return None
        return entry.model_copy(update={"path": path, "original_path": original})

    def _filter_paths(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        filtered: list[str] = []
        for path in paths:
            relative = self._workspace_path(path)
            if relative is not None and not self.protected.is_protected(Path(relative)):
                filtered.append(relative)
        return tuple(filtered)

    def _binary_paths(self, payload: bytes) -> tuple[str, ...]:
        paths: list[str] = []
        records = payload.split(b"\0")
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            fields = record.split(b"\t", 2)
            if len(fields) != 3 or fields[0] != b"-" or fields[1] != b"-":
                continue
            paths.extend([os.fsdecode(fields[2])])
            if index < len(records) and records[index] and b"\t" not in records[index]:
                index += 1
        return self._filter_paths(tuple(paths))

    def _workspace_path(self, repository_path: str | None) -> str | None:
        if repository_path is None:
            return None
        parsed = PurePosixPath(repository_path)
        if parsed.is_absolute() or ".." in parsed.parts:
            return None
        prefix = self.repository.workspace_prefix
        if prefix == ".":
            return repository_path
        marker = f"{prefix}/"
        if repository_path == prefix:
            return "."
        if not repository_path.startswith(marker):
            return None
        return repository_path.removeprefix(marker)

    def _operation_state(self) -> str:
        git_dir = Path(self.repository.git_dir)
        markers = (
            ("merge", "MERGE_HEAD"),
            ("cherry_pick", "CHERRY_PICK_HEAD"),
            ("revert", "REVERT_HEAD"),
            ("bisect", "BISECT_LOG"),
        )
        for state, marker in markers:
            if (git_dir / marker).exists():
                return state
        if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
            return "rebase"
        return "clean"

    def _environment(self) -> dict[str, str]:
        return build_child_environment(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
            },
            purpose="git",
            source=self.environment,
        ).values


def _decode_output(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace")


def _decode_field(payload: bytes) -> str:
    return payload.decode("utf-8", errors="strict")


def _nul_paths(payload: bytes) -> tuple[str, ...]:
    return tuple(os.fsdecode(item) for item in payload.split(b"\0") if item)


def _parse_track(value: str) -> tuple[int, int]:
    ahead_match = re.search(r"ahead (\d+)", value)
    behind_match = re.search(r"behind (\d+)", value)
    return (
        int(ahead_match.group(1)) if ahead_match else 0,
        int(behind_match.group(1)) if behind_match else 0,
    )
