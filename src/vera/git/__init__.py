"""Core-owned native Git capabilities."""

from vera.git.commit import GitCommitResult, GitCommitter, GitCommitTransactionError
from vera.git.commit_plan import GitCommitPlan, GitCommitPlanBuilder, GitCommitPlanError
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
    "GitCommitPlan",
    "GitCommitPlanBuilder",
    "GitCommitPlanError",
    "GitCommitSummary",
    "GitCommitResult",
    "GitCommitter",
    "GitCommitTransactionError",
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
