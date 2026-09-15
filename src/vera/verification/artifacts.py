"""Plan verification artifact roots and rewrite known command profiles."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vera.contracts.verification import VerificationArtifactPlan, VerificationCommand

CleanupStatus = Literal["cleaned", "skipped", "failed"]

_INDEX_WIDTH = 3
_INSTALL_PREFIX_LEN = 12
_UNAVAILABLE = "verification_artifact_isolation_unavailable"
_INSIDE_WORKSPACE = "verification_output_inside_workspace"
_NOT_OWNED = "verification_output_not_owned"
_UNSAFE_ROOT = "verification_artifact_root_unsafe"
_SUGGEST_PROFILE = (
    "use a supported no-write command, add an isolation profile, "
    "or move expected workspace writes into a Change Set"
)
_XCODE_ASSIGNMENTS = ("SYMROOT", "OBJROOT", "SHARED_PRECOMPS_DIR", "DSTROOT")


def _unavailable(basename: str) -> VerificationArtifactError:
    return VerificationArtifactError(_UNAVAILABLE, basename=basename, suggestion=_SUGGEST_PROFILE)


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


def environment_for_plan(plan: VerificationArtifactPlan) -> dict[str, str]:
    root = plan.root or ""
    if plan.profile == "pytest":
        return {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_ADDOPTS": "-p no:cacheprovider",
            "COVERAGE_FILE": f"{root}/.coverage",
        }
    if plan.profile == "xcode":
        return {"CLANG_MODULE_CACHE_PATH": f"{root}/ModuleCache"}
    if plan.profile == "git_readonly":
        return {"GIT_OPTIONAL_LOCKS": "0"}
    return {}


@dataclass(frozen=True)
class CleanupResult:
    status: CleanupStatus
    code: str | None = None


class VerificationArtifactRoot:
    def __init__(self, prefix: Path | None = None) -> None:
        self.prefix = (prefix or default_verification_prefix()).resolve()

    def prepare(
        self,
        *,
        workspace_root: Path,
        installation_id: str,
        run_id: str,
        index: int,
    ) -> Path:
        root = artifact_root(
            workspace_root=workspace_root,
            installation_id=installation_id,
            run_id=run_id,
            index=index,
            prefix=self.prefix,
        )
        self._create_exact_root(root)
        return root

    def prepare_existing(self, root: Path, *, workspace_root: Path) -> Path:
        candidate = Path(root)
        self._validate_owned_root(candidate, workspace_root=workspace_root)
        if candidate.exists() and candidate.is_dir() and not candidate.is_symlink():
            return candidate.resolve()
        self._create_exact_root(candidate)
        return candidate.resolve()

    def cleanup(self, root: str | Path, *, workspace_root: Path) -> CleanupResult:
        candidate = Path(root)
        try:
            self._validate_owned_root(candidate, workspace_root=workspace_root, for_cleanup=True)
        except VerificationArtifactError:
            return CleanupResult(status="failed", code="artifact_cleanup_failed")
        if not candidate.exists():
            return CleanupResult(status="cleaned")
        try:
            shutil.rmtree(candidate)
        except OSError:
            return CleanupResult(status="failed", code="artifact_cleanup_failed")
        return CleanupResult(status="cleaned")

    def _create_exact_root(self, root: Path) -> None:
        current = Path(root.anchor) if root.anchor else Path("/")
        created: list[Path] = []
        for part in root.parts[1:]:
            current = current / part
            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise VerificationArtifactError(_UNSAFE_ROOT)
                continue
            os.mkdir(current, 0o700)
            os.chmod(current, 0o700)
            created.append(current)
        final = root
        if final.is_symlink() or not final.is_dir():
            raise VerificationArtifactError(_UNSAFE_ROOT)

    def _validate_owned_root(
        self,
        root: Path,
        *,
        workspace_root: Path,
        for_cleanup: bool = False,
    ) -> None:
        if root.is_symlink():
            raise VerificationArtifactError(_UNSAFE_ROOT)
        try:
            resolved = root.resolve()
        except OSError as exc:
            raise VerificationArtifactError(_UNSAFE_ROOT) from exc
        if not _is_relative_to(resolved, self.prefix):
            raise VerificationArtifactError(_UNSAFE_ROOT)
        workspace = workspace_root.expanduser().resolve()
        if _is_relative_to(resolved, workspace):
            raise VerificationArtifactError(_INSIDE_WORKSPACE)
        if for_cleanup and root.exists() and not root.is_dir():
            raise VerificationArtifactError(_UNSAFE_ROOT)
        relative = resolved.relative_to(self.prefix)
        if len(relative.parts) != 3:
            raise VerificationArtifactError(_UNSAFE_ROOT)
        install, run_id, index = relative.parts
        if len(install) != _INSTALL_PREFIX_LEN or not _safe_run_id(run_id):
            raise VerificationArtifactError(_UNSAFE_ROOT)
        if not (index.isdigit() and len(index) == _INDEX_WIDTH):
            raise VerificationArtifactError(_UNSAFE_ROOT)
        current = self.prefix
        for part in relative.parts[:-1]:
            current = current / part
            if current.exists() and (current.is_symlink() or not current.is_dir()):
                raise VerificationArtifactError(_UNSAFE_ROOT)


class VerificationArtifactPlanner:
    def __init__(self, prefix: Path | None = None) -> None:
        self.prefix = prefix

    def plan(
        self,
        command: VerificationCommand,
        *,
        workspace_root: Path,
        installation_id: str,
        run_id: str,
        index: int,
    ) -> VerificationCommand:
        root = artifact_root(
            workspace_root=workspace_root,
            installation_id=installation_id,
            run_id=run_id,
            index=index,
            prefix=self.prefix,
        )
        workspace = workspace_root.expanduser().resolve()
        tool, tokens = _tool_tokens(command.argv)
        basename = Path(tool).name if tool else ""
        if _is_xcode(tool, tokens):
            return self._plan_xcode(command, root=root, workspace=workspace, basename=basename)
        if _is_swiftpm(tool, tokens):
            return self._plan_swiftpm(command, root=root, workspace=workspace, basename=basename)
        if _is_pytest(tool, tokens):
            return self._plan_pytest(command, root=root, workspace=workspace, basename=basename)
        if _is_mypy(tool, tokens):
            return self._plan_mypy(command, root=root, workspace=workspace, basename=basename)
        if _is_ruff(tool, tokens):
            return self._plan_ruff(command, root=root, workspace=workspace, basename=basename)
        if _is_git(tool, tokens):
            return self._plan_git(command, root=root, basename=basename)
        if _is_tsc(tool, tokens):
            return self._plan_tsc(command, root=root, basename=basename)
        raise VerificationArtifactError(
            _UNAVAILABLE,
            basename=basename,
            suggestion=_SUGGEST_PROFILE,
        )

    def _planned(
        self,
        command: VerificationCommand,
        *,
        argv: tuple[str, ...],
        profile: str,
        root: Path,
    ) -> VerificationCommand:
        return command.model_copy(
            update={
                "argv": argv,
                "artifact_plan": VerificationArtifactPlan(
                    profile=profile,  # type: ignore[arg-type]
                    root=str(root),
                ),
            }
        )

    def _plan_xcode(
        self,
        command: VerificationCommand,
        *,
        root: Path,
        workspace: Path,
        basename: str,
    ) -> VerificationCommand:
        argv = list(command.argv)
        derived = _flag_values(argv, "-derivedDataPath")
        settings = _assignment_values(argv, set(_XCODE_ASSIGNMENTS))
        for raw in (*derived, *settings.values()):
            self._require_owned_output(raw, root=root, workspace=workspace, basename=basename)
        has_scheme = "-scheme" in argv
        has_target = "-target" in argv
        if has_scheme:
            if not derived:
                argv.append("-derivedDataPath")
                argv.append(str(root / "DerivedData"))
            return self._planned(command, argv=tuple(argv), profile="xcode", root=root)
        if has_target:
            if "SYMROOT" not in settings:
                argv.append(f"SYMROOT={root / 'Build' / 'Products'}")
            if "OBJROOT" not in settings:
                argv.append(f"OBJROOT={root / 'Build' / 'Intermediates'}")
            if "SHARED_PRECOMPS_DIR" not in settings:
                argv.append(f"SHARED_PRECOMPS_DIR={root / 'Build' / 'SharedPrecomps'}")
            if "DSTROOT" not in settings:
                argv.append(f"DSTROOT={root / 'Build' / 'Uninstalled'}")
            return self._planned(command, argv=tuple(argv), profile="xcode", root=root)
        raise _unavailable(basename)

    def _plan_swiftpm(
        self,
        command: VerificationCommand,
        *,
        root: Path,
        workspace: Path,
        basename: str,
    ) -> VerificationCommand:
        argv = list(command.argv)
        scratch = _flag_values(argv, "--scratch-path")
        expected = root / "swiftpm"
        for raw in scratch:
            self._require_owned_output(raw, root=root, workspace=workspace, basename=basename)
        if not scratch:
            argv.extend(["--scratch-path", str(expected)])
        return self._planned(command, argv=tuple(argv), profile="swiftpm", root=root)

    def _plan_pytest(
        self,
        command: VerificationCommand,
        *,
        root: Path,
        workspace: Path,
        basename: str,
    ) -> VerificationCommand:
        del workspace
        tokens = list(command.argv)
        lowered = {token.lower() for token in tokens}
        forbidden = (
            "--snapshot-update",
            "--overwrite-snapshots",
            "--update-snapshots",
        )
        if any(item in lowered for item in forbidden):
            raise _unavailable(basename)
        for token in tokens:
            if token.startswith("--cov-report") and "html" in token.lower():
                raise VerificationArtifactError(
                    _UNAVAILABLE, basename=basename, suggestion=_SUGGEST_PROFILE
                )
        return self._planned(command, argv=command.argv, profile="pytest", root=root)

    def _plan_mypy(
        self,
        command: VerificationCommand,
        *,
        root: Path,
        workspace: Path,
        basename: str,
    ) -> VerificationCommand:
        argv = list(command.argv)
        caches = _flag_values(argv, "--cache-dir")
        expected = root / "mypy"
        for raw in caches:
            self._require_owned_output(raw, root=root, workspace=workspace, basename=basename)
        if not caches:
            argv.extend(["--cache-dir", str(expected)])
        return self._planned(command, argv=tuple(argv), profile="mypy", root=root)

    def _plan_ruff(
        self,
        command: VerificationCommand,
        *,
        root: Path,
        workspace: Path,
        basename: str,
    ) -> VerificationCommand:
        del workspace
        argv = [token for token in command.argv if token != "--no-cache"]
        if "--fix" in argv or any(token.startswith("--fix") for token in argv):
            raise _unavailable(basename)
        if not _ruff_is_readonly(argv):
            raise _unavailable(basename)
        argv.append("--no-cache")
        return self._planned(command, argv=tuple(argv), profile="ruff_no_cache", root=root)

    def _plan_git(
        self, command: VerificationCommand, *, root: Path, basename: str
    ) -> VerificationCommand:
        argv = command.argv
        if argv in {("git", "diff", "--check"), ("git", "status")}:
            return self._planned(command, argv=argv, profile="git_readonly", root=root)
        raise _unavailable(basename)

    def _plan_tsc(
        self, command: VerificationCommand, *, root: Path, basename: str
    ) -> VerificationCommand:
        argv = command.argv
        if _tsc_is_readonly(argv):
            return self._planned(command, argv=argv, profile="tsc_no_emit", root=root)
        raise _unavailable(basename)

    def _require_owned_output(
        self,
        raw: str,
        *,
        root: Path,
        workspace: Path,
        basename: str,
    ) -> None:
        located = _resolve_output_path(raw, workspace=workspace)
        if _is_relative_to(located, workspace):
            raise VerificationArtifactError(_INSIDE_WORKSPACE, basename=basename)
        home = Path.home().resolve()
        if _is_relative_to(located, home) or located == home:
            raise VerificationArtifactError(_NOT_OWNED, basename=basename)
        if not _is_relative_to(located, root):
            raise VerificationArtifactError(_NOT_OWNED, basename=basename)


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
