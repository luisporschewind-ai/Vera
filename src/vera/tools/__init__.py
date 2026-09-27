"""Built-in tools exposed by Vera Core.

Git tool exports are lazy so recovery models can be imported before the Git
receipt and snapshot modules without creating an import cycle.
"""

from typing import TYPE_CHECKING, Any

from vera.tools.bash import BashTool
from vera.tools.definitions import ToolDefinition, ToolDefinitionV2, ToolResult
from vera.tools.registry import DuplicateToolError, ToolRegistry

_GIT_EXPORTS = frozenset(
    {
        "GitBranchListTool",
        "GitCommitTool",
        "GitDiffTool",
        "GitLogTool",
        "GitRepositoryInitTool",
        "GitShowTool",
        "GitStatusTool",
    }
)

if TYPE_CHECKING:
    from vera.tools.git import (
        GitBranchListTool,
        GitCommitTool,
        GitDiffTool,
        GitLogTool,
        GitRepositoryInitTool,
        GitShowTool,
        GitStatusTool,
    )


def __getattr__(name: str) -> Any:
    if name in _GIT_EXPORTS:
        from vera.tools import git

        value = getattr(git, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BashTool",
    "GitBranchListTool",
    "GitCommitTool",
    "GitDiffTool",
    "GitLogTool",
    "GitRepositoryInitTool",
    "GitShowTool",
    "GitStatusTool",
    "DuplicateToolError",
    "ToolDefinition",
    "ToolDefinitionV2",
    "ToolRegistry",
    "ToolResult",
]
