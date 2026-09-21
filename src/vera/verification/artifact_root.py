"""Owned verification artifact-root lifecycle."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vera.contracts.verification import VerificationArtifactPlan
from vera.verification.artifact_paths import (
    _INDEX_WIDTH,
    _INSIDE_WORKSPACE,
    _INSTALL_PREFIX_LEN,
    _UNSAFE_ROOT,
    VerificationArtifactError,
    _is_relative_to,
    _safe_run_id,
    artifact_root,
    default_verification_prefix,
)

CleanupStatus = Literal["cleaned", "skipped", "failed"]


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
