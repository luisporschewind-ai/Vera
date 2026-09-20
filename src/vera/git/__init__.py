"""Core-owned, read-only native Git capabilities."""

from vera.git.discovery import GitDiscovery, GitDiscoveryError
from vera.git.models import (
    GitBranchSummary,
    GitCommitSummary,
    GitDiffRequest,
    GitDiffResult,
    GitLogRequest,
    GitRepositoryInfo,
    GitRepositorySnapshot,
    GitShowRequest,
    GitShowResult,
    GitStatusEntry,
)
from vera.git.service import GitService, GitServiceError

__all__ = [
    "GitBranchSummary",
    "GitCommitSummary",
    "GitDiffRequest",
    "GitDiffResult",
    "GitDiscovery",
    "GitDiscoveryError",
    "GitLogRequest",
    "GitRepositoryInfo",
    "GitRepositorySnapshot",
    "GitService",
    "GitServiceError",
    "GitShowRequest",
    "GitShowResult",
    "GitStatusEntry",
]
