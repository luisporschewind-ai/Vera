"""Resolve workspace-relative paths without allowing boundary escapes."""

from pathlib import Path


class WorkspaceBoundaryError(ValueError):
    """Raised when a path is outside the workspace or violates policy."""


BUILT_IN_PROTECTED_NAMES = frozenset({".env", ".npmrc", ".pypirc", "credentials"})
BUILT_IN_PROTECTED_SUFFIXES = (".pem", ".key", ".p12")
SAFE_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})


class ProtectedPathPolicy:
    """Small, deterministic policy for files that may contain credentials."""

    def __init__(
        self,
        names: frozenset[str] = BUILT_IN_PROTECTED_NAMES,
        suffixes: tuple[str, ...] = BUILT_IN_PROTECTED_SUFFIXES,
    ) -> None:
        self.names = names
        self.suffixes = suffixes

    def is_protected(self, relative: Path) -> bool:
        name = relative.name
        if name in SAFE_ENV_TEMPLATES:
            return False
        return name in self.names or name.endswith(self.suffixes)


class WorkspacePaths:
    """Canonical path resolver for read and mutation operations."""

    def __init__(self, root: Path, protected: ProtectedPathPolicy | None = None) -> None:
        self.root = root.expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise WorkspaceBoundaryError(f"workspace is not a directory: {root}")
        self.protected = protected or ProtectedPathPolicy()

    @staticmethod
    def _relative(raw_path: str) -> Path:
        if not raw_path or not raw_path.strip():
            raise WorkspaceBoundaryError("path must not be empty")
        normalized = raw_path.replace("\\", "/")
        relative = Path(normalized)
        if relative.is_absolute() or any(part == ".." for part in relative.parts):
            raise WorkspaceBoundaryError(f"path must be workspace-relative: {raw_path}")
        return relative

    def _within_root(self, candidate: Path) -> Path:
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceBoundaryError("path escapes workspace") from exc
        return candidate

    def resolve_read(self, raw_path: str) -> Path:
        relative = self._relative(raw_path)
        if self.protected.is_protected(relative):
            raise WorkspaceBoundaryError(f"protected path: {raw_path}")
        return self._within_root((self.root / relative).resolve(strict=False))

    def resolve_mutation(self, raw_path: str) -> Path:
        relative = self._relative(raw_path)
        if self.protected.is_protected(relative):
            raise WorkspaceBoundaryError(f"protected path: {raw_path}")
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspaceBoundaryError(f"symlink is not allowed for mutation: {raw_path}")
        return self._within_root((self.root / relative).resolve(strict=False))
