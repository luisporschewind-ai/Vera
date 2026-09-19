"""Read-only filesystem tools constrained to a workspace."""

from pathlib import Path, PurePosixPath

from pydantic import Field

from vera.tools.definitions import ToolResult
from vera.workspace.paths import WorkspaceBoundaryError, WorkspacePaths

_IGNORED_DIRECTORIES = frozenset({".git", ".venv", "node_modules", "dist", "build", ".vera"})


class ReadFileResult(ToolResult):
    content: str | None = None


class DirectoryResult(ToolResult):
    entries: list[str] = Field(default_factory=list)


class SearchMatch(ToolResult):
    path: str
    line: int
    text: str


class SearchResult(ToolResult):
    matches: list[SearchMatch] = Field(default_factory=list)


class FindResult(ToolResult):
    paths: list[str] = Field(default_factory=list)


def read_file(paths: WorkspacePaths, path: str, max_bytes: int = 100_000) -> ReadFileResult:
    try:
        target = paths.resolve_read(path)
    except WorkspaceBoundaryError:
        return ReadFileResult(ok=False, error_code="workspace_boundary")
    if not target.is_file():
        return ReadFileResult(ok=False, error_code="not_a_file")
    try:
        data = target.read_bytes()
        truncated = len(data) > max_bytes
        text = data[:max_bytes].decode("utf-8")
        if "\x00" in text:
            raise UnicodeDecodeError("utf-8", data, 0, 1, "binary content")
    except (OSError, UnicodeDecodeError):
        return ReadFileResult(ok=False, error_code="binary_or_non_utf8")
    return ReadFileResult(ok=True, content=text, truncated=truncated)


def list_directory(paths: WorkspacePaths, path: str = ".") -> DirectoryResult:
    try:
        target = paths.resolve_read(path)
    except WorkspaceBoundaryError:
        return DirectoryResult(ok=False, error_code="workspace_boundary")
    if not target.is_dir():
        return DirectoryResult(ok=False, error_code="not_a_directory")
    try:
        entries = sorted(
            (item.name for item in target.iterdir()),
            key=lambda name: (name.startswith("."), name),
        )
    except OSError:
        return DirectoryResult(ok=False, error_code="io_error")
    return DirectoryResult(ok=True, entries=entries)


def search_text(paths: WorkspacePaths, query: str, path: str = ".") -> SearchResult:
    if not query:
        return SearchResult(ok=False, error_code="empty_query")
    try:
        root = paths.resolve_read(path)
    except WorkspaceBoundaryError:
        return SearchResult(ok=False, error_code="workspace_boundary")
    matches: list[SearchMatch] = []
    if root.is_file():
        _collect_search_matches(paths, root, query, matches)
        return SearchResult(ok=True, matches=matches)
    if not root.is_dir():
        return SearchResult(ok=False, error_code="not_found")
    for file_path in sorted(root.rglob("*")):
        _collect_search_matches(paths, file_path, query, matches)
    return SearchResult(ok=True, matches=matches)


def find_files(paths: WorkspacePaths, pattern: str = "*", path: str = ".") -> FindResult:
    """Discover regular files using a workspace-relative glob, in stable order."""

    normalized_pattern = pattern.replace("\\", "/")
    pattern_path = PurePosixPath(normalized_pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        return FindResult(ok=False, error_code="workspace_boundary")
    try:
        root = paths.resolve_read(path)
    except WorkspaceBoundaryError:
        return FindResult(ok=False, error_code="workspace_boundary")
    if root.is_file():
        relative = root.relative_to(paths.root)
        return FindResult(
            ok=True,
            paths=[relative.as_posix()] if root.match(normalized_pattern) else [],
        )
    if not root.is_dir():
        return FindResult(ok=False, error_code="not_found")
    found: list[str] = []
    for file_path in sorted(root.rglob(normalized_pattern)):
        relative = file_path.relative_to(paths.root)
        if (
            file_path.is_symlink()
            or not file_path.is_file()
            or any(part in _IGNORED_DIRECTORIES for part in relative.parts)
        ):
            continue
        if paths.protected.is_protected(relative):
            continue
        found.append(relative.as_posix())
    return FindResult(ok=True, paths=found)


def _collect_search_matches(
    paths: WorkspacePaths,
    file_path: Path,
    query: str,
    matches: list[SearchMatch],
) -> None:
    relative = file_path.relative_to(paths.root)
    if (
        file_path.is_symlink()
        or not file_path.is_file()
        or any(part in _IGNORED_DIRECTORIES for part in relative.parts)
    ):
        return
    if paths.protected.is_protected(relative):
        return
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return
    for line_number, line in enumerate(lines, start=1):
        if query in line:
            matches.append(
                SearchMatch(
                    ok=True,
                    path=relative.as_posix(),
                    line=line_number,
                    text=line,
                )
            )
