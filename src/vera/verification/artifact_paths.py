"""Path and executable helpers for verification artifacts."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

_INDEX_WIDTH = 3
_INSTALL_PREFIX_LEN = 12
_UNAVAILABLE = "verification_artifact_isolation_unavailable"
_INSIDE_WORKSPACE = "verification_output_inside_workspace"
_NOT_OWNED = "verification_output_not_owned"
_UNSAFE_ROOT = "verification_artifact_root_unsafe"
_MISSING = "verification_executable_missing"
_SUGGEST_PROFILE = (
    "use a supported no-write command, add an isolation profile, "
    "or move expected workspace writes into a Change Set"
)
_SUGGEST_MISSING = (
    "install the tool in the workspace virtualenv, use a PATH executable, or omit verification"
)
_XCODE_ASSIGNMENTS = ("SYMROOT", "OBJROOT", "SHARED_PRECOMPS_DIR", "DSTROOT")


class VerificationArtifactError(ValueError):
    """Stable planner failure with a basename and suggestion, not secret argv."""

    def __init__(self, code: str, *, basename: str = "", suggestion: str = "") -> None:
        self.code = code
        self.basename = basename
        self.suggestion = suggestion
        super().__init__(code)


def default_verification_prefix() -> Path:
    if sys.platform == "darwin":
        return Path("/private/tmp/vera-verification")
    return Path(tempfile.gettempdir()).resolve() / "vera-verification"


def installation_prefix(installation_id: str) -> str:
    return hashlib.sha256(installation_id.encode("utf-8")).hexdigest()[:_INSTALL_PREFIX_LEN]


def artifact_root(
    *,
    workspace_root: Path,
    installation_id: str,
    run_id: str,
    index: int,
    prefix: Path | None = None,
) -> Path:
    if index < 0:
        raise VerificationArtifactError(_UNSAFE_ROOT)
    if not _safe_run_id(run_id):
        raise VerificationArtifactError(_UNSAFE_ROOT)
    base = (prefix or default_verification_prefix()).resolve()
    root = base / installation_prefix(installation_id) / run_id / f"{index:0{_INDEX_WIDTH}d}"
    workspace = workspace_root.expanduser().resolve()
    if _is_relative_to(root, workspace):
        raise VerificationArtifactError(_INSIDE_WORKSPACE)
    return root


def _safe_run_id(run_id: str) -> bool:
    if not run_id or run_id in {".", ".."}:
        return False
    if any(separator in run_id for separator in ("/", "\\", os.sep, "\x00")):
        return False
    return ".." not in run_id


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _resolve_output_path(raw: str, *, workspace: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    if candidate.exists() or candidate.parent.exists():
        return candidate.resolve()
    return Path(os.path.normpath(str(candidate)))


def workspace_bin_dirs(workspace: Path) -> tuple[Path, ...]:
    if sys.platform == "win32":
        relatives = (Path(".venv") / "Scripts", Path("venv") / "Scripts")
    else:
        relatives = (Path(".venv") / "bin", Path("venv") / "bin")
    found: list[Path] = []
    for relative in relatives:
        directory = workspace / relative
        if directory.is_dir():
            found.append(directory)
    return tuple(found)


def workspace_tool_path(workspace: Path, argv0: str) -> Path | None:
    name = Path(argv0).name
    if not name or Path(argv0).is_absolute():
        return None
    for directory in workspace_bin_dirs(workspace):
        candidate = directory / name
        if _is_executable_file(candidate):
            return candidate
    return None


def with_workspace_runtime_path(values: dict[str, str], workspace: Path) -> dict[str, str]:
    updated = dict(values)
    directories = workspace_bin_dirs(workspace)
    if not directories:
        return updated
    prefix = os.pathsep.join(str(item) for item in directories)
    current = updated.get("PATH", "")
    updated["PATH"] = prefix if not current else f"{prefix}{os.pathsep}{current}"
    if "VIRTUAL_ENV" not in updated:
        updated["VIRTUAL_ENV"] = str(directories[0].parent)
    return updated


def _is_executable_file(path: Path) -> bool:
    try:
        return path.exists() and not path.is_dir() and os.access(path, os.X_OK)
    except OSError:
        return False


def _workspace_managed_tool(argv0: str) -> bool:
    name = Path(argv0).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name in {"ruff", "pytest", "mypy"} or _is_python(name)


def _require_resolvable_executable(workspace: Path, argv0: str, basename: str) -> None:
    if not argv0:
        raise VerificationArtifactError(_MISSING, basename=basename, suggestion=_SUGGEST_MISSING)
    located = Path(argv0)
    if located.is_absolute() and _is_executable_file(located):
        return
    if workspace_tool_path(workspace, argv0) is not None:
        return
    if shutil.which(argv0) is not None:
        return
    raise VerificationArtifactError(_MISSING, basename=basename, suggestion=_SUGGEST_MISSING)


def _tool_tokens(argv: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    if not argv:
        return "", ()
    first = Path(argv[0]).name
    if first == "xcrun" and len(argv) > 1:
        return argv[1], argv[1:]
    return argv[0], argv


def _is_python(name: str) -> bool:
    lowered = name.lower()
    return lowered == "python" or lowered.startswith("python3")


def _is_xcode(tool: str, tokens: tuple[str, ...]) -> bool:
    del tokens
    return Path(tool).name == "xcodebuild"


def _is_swiftpm(tool: str, tokens: tuple[str, ...]) -> bool:
    name = Path(tool).name
    if name != "swift":
        return False
    return len(tokens) >= 2 and tokens[1] in {"build", "test"}


def _is_pytest(tool: str, tokens: tuple[str, ...]) -> bool:
    name = Path(tool).name
    if name == "pytest":
        return True
    return _is_python(name) and len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] == "pytest"


def _is_mypy(tool: str, tokens: tuple[str, ...]) -> bool:
    name = Path(tool).name
    if name == "mypy":
        return True
    return _is_python(name) and len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] == "mypy"


def _is_ruff(tool: str, tokens: tuple[str, ...]) -> bool:
    del tokens
    return Path(tool).name == "ruff"


def _is_git(tool: str, tokens: tuple[str, ...]) -> bool:
    del tokens
    return Path(tool).name == "git"


def _is_tsc(tool: str, tokens: tuple[str, ...]) -> bool:
    del tokens
    return Path(tool).name == "tsc"


def _ruff_is_readonly(argv: list[str]) -> bool:
    return "check" in argv or ("format" in argv and "--check" in argv)


def _tsc_is_readonly(argv: tuple[str, ...]) -> bool:
    has_no_emit = "--noEmit" in argv or "--no-emit" in argv
    has_incremental_false = False
    for index, token in enumerate(argv):
        if token in {"--incremental", "-incremental"} and index + 1 < len(argv):
            has_incremental_false = argv[index + 1] == "false"
        if token in {"--incremental=false", "-incremental=false"}:
            has_incremental_false = True
    return has_no_emit and has_incremental_false


def _flag_values(argv: list[str], flag: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == flag:
            if index + 1 < len(argv):
                values.append(argv[index + 1])
            index += 2
            continue
        prefix = f"{flag}="
        if token.startswith(prefix):
            values.append(token[len(prefix) :])
        index += 1
    return values


def _assignment_values(argv: list[str], keys: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for token in argv:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in keys:
            found[key] = value
    return found
