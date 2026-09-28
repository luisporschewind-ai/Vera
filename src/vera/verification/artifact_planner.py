"""Verification command artifact planner."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.verification import VerificationArtifactPlan, VerificationCommand
from vera.verification.artifact_paths import (
    _INSIDE_WORKSPACE,
    _NOT_OWNED,
    _SUGGEST_PROFILE,
    _UNAVAILABLE,
    _XCODE_ASSIGNMENTS,
    VerificationArtifactError,
    _assignment_values,
    _flag_values,
    _is_git,
    _is_mypy,
    _is_pytest,
    _is_relative_to,
    _is_ruff,
    _is_swiftpm,
    _is_tsc,
    _is_xcode,
    _require_resolvable_executable,
    _resolve_output_path,
    _ruff_is_readonly,
    _tool_tokens,
    _tsc_is_readonly,
    _workspace_managed_tool,
    artifact_root,
)


def _unavailable(basename: str) -> VerificationArtifactError:
    return VerificationArtifactError(_UNAVAILABLE, basename=basename, suggestion=_SUGGEST_PROFILE)


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
            planned = self._plan_xcode(command, root=root, workspace=workspace, basename=basename)
        elif _is_swiftpm(tool, tokens):
            planned = self._plan_swiftpm(command, root=root, workspace=workspace, basename=basename)
        elif _is_pytest(tool, tokens):
            planned = self._plan_pytest(command, root=root, workspace=workspace, basename=basename)
        elif _is_mypy(tool, tokens):
            planned = self._plan_mypy(command, root=root, workspace=workspace, basename=basename)
        elif _is_ruff(tool, tokens):
            planned = self._plan_ruff(command, root=root, workspace=workspace, basename=basename)
        elif _is_git(tool, tokens):
            planned = self._plan_git(command, root=root, basename=basename)
        elif _is_tsc(tool, tokens):
            planned = self._plan_tsc(command, root=root, basename=basename)
        else:
            raise VerificationArtifactError(
                _UNAVAILABLE,
                basename=basename,
                suggestion=_SUGGEST_PROFILE,
            )
        argv0 = planned.argv[0] if planned.argv else ""
        if _workspace_managed_tool(argv0):
            _require_resolvable_executable(workspace, argv0, basename)
        return planned

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
