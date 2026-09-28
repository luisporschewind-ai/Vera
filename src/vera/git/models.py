"""Structured models for native Git read capabilities."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from vera.contracts import ContractModel


class GitRepositoryInfo(ContractModel):
    repository_root: str
    workspace_prefix: str
    git_dir: str
    bare: bool


class GitStatusEntry(ContractModel):
    path: str
    original_path: str | None = None
    staged: str = " "
    unstaged: str = " "
    untracked: bool = False
    ignored: bool = False
    conflicted: bool = False
    submodule: str | None = None


class GitRepositorySnapshot(ContractModel):
    repository_root: str
    workspace_prefix: str
    head_oid: str | None
    branch: str | None
    detached: bool
    unborn: bool
    upstream: str | None
    ahead: int = Field(ge=0)
    behind: int = Field(ge=0)
    operation_state: str
    entries: tuple[GitStatusEntry, ...]


class GitDiffResult(ContractModel):
    scope: Literal["working", "staged", "head", "range"]
    patch: str
    files: tuple[str, ...]
    truncated: bool = False
    binary_files: tuple[str, ...] = ()


class GitCommitSummary(ContractModel):
    oid: str
    parent_oids: tuple[str, ...]
    author_name: str
    authored_at: datetime
    subject: str


class GitShowResult(ContractModel):
    commit: GitCommitSummary
    files: tuple[str, ...]
    diff: GitDiffResult


class GitBranchSummary(ContractModel):
    name: str
    current: bool
    oid: str
    upstream: str | None
    ahead: int = Field(ge=0)
    behind: int = Field(ge=0)


class GitDiffRequest(ContractModel):
    scope: Literal["working", "staged", "head", "range"]
    base: str | None = None
    target: str | None = None
    paths: tuple[str, ...] = ()
    context_lines: int = Field(default=3, ge=0, le=100)
    stat_only: bool = False


class GitLogRequest(ContractModel):
    ref: str = "HEAD"
    limit: int = Field(default=20, ge=1, le=20)
    paths: tuple[str, ...] = ()


class GitShowRequest(ContractModel):
    ref: str
    paths: tuple[str, ...] = ()
    context_lines: int = Field(default=3, ge=0, le=100)
