"""Bounded external editor launch. No shell interpolation."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class ExternalEditorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExternalEditorResult:
    path: Path
    text: str
    changed: bool
    status: Literal["ok", "unchanged", "failed", "cancelled"]


class ExternalEditor:
    def __init__(self, argv: tuple[str, ...], directory: Path) -> None:
        if not argv:
            raise ExternalEditorError("editor_unconfigured", "no editor argv configured")
        if any(token in part for part in argv for token in ("`", "$(", "${", "|", ";")):
            raise ExternalEditorError(
                "editor_forbidden",
                "editor argv must not contain shell syntax",
            )
        self.argv = argv
        self.directory = directory

    def preview(self) -> tuple[str, ...]:
        return (*self.argv, "<draft>")

    def write_draft(self, text: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="vera-draft-",
            suffix=".md",
            dir=self.directory,
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            path = Path(handle.name)
        os.chmod(path, 0o600)
        return path

    def run(self, path: Path, *, runner: object | None = None) -> ExternalEditorResult:
        before = path.read_text(encoding="utf-8") if path.is_file() else ""
        argv = (*self.argv, str(path))
        try:
            if runner is None:
                completed = subprocess.run(argv, check=False, shell=False)
                code = completed.returncode
            else:
                code = int(runner(argv))  # type: ignore[operator]
        except OSError as exc:
            raise ExternalEditorError("editor_failed", str(exc)) from exc
        if code != 0:
            return ExternalEditorResult(path=path, text=before, changed=False, status="failed")
        after = path.read_text(encoding="utf-8") if path.is_file() else before
        if after == before:
            return ExternalEditorResult(path=path, text=after, changed=False, status="unchanged")
        return ExternalEditorResult(path=path, text=after, changed=True, status="ok")

    def cleanup(self, path: Path) -> None:
        if path.parent.resolve() != self.directory.resolve():
            raise ExternalEditorError(
                "cleanup_refused",
                "refusing to delete a path outside draft dir",
            )
        if path.exists():
            path.unlink()
