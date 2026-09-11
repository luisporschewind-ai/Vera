"""Copy evaluation fixtures into a throwaway workspace and state directory."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from vera.evals.corpus import LoadedEvalCase

_DIR_MODE = 0o700
_FILE_MODE = 0o600


def _mkdir(path: Path) -> None:
    path.mkdir(mode=_DIR_MODE)
    os.chmod(path, _DIR_MODE)


class IsolationError(ValueError):
    def __init__(self, code: str, path: Path | str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.path = Path(path)
        self.message = message


def _fail(code: str, path: Path | str, message: str) -> NoReturn:
    raise IsolationError(code, path, message)


@dataclass
class IsolatedEvalCase:
    workspace: Path
    state_dir: Path
    staging_dir: Path
    source_manifest_hash: str
    case_root: Path
    temp_root: Path

    def verify_source_unchanged(self, current_manifest_hash: str) -> None:
        if current_manifest_hash != self.source_manifest_hash:
            _fail("source_changed", self.workspace, "source corpus changed after isolation")

    def cleanup(self) -> None:
        if not self.case_root.exists():
            return
        try:
            self.case_root.resolve().relative_to(self.temp_root.resolve())
        except ValueError:
            _fail("cleanup_refused", self.case_root, "refusing to delete a path outside temp_root")
        shutil.rmtree(self.case_root)


class FixtureIsolator:
    def __init__(self, temp_root: Path) -> None:
        self.temp_root = temp_root

    def prepare(self, loaded: LoadedEvalCase) -> IsolatedEvalCase:
        self.temp_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.temp_root, _DIR_MODE)
        before = set(self.temp_root.iterdir())
        created = Path(tempfile.mkdtemp(prefix="vera-eval-", dir=self.temp_root))
        if created in before:
            _fail("destination_exists", created, "evaluation temp directory already exists")
        try:
            os.chmod(created, _DIR_MODE)
            workspace = created / "workspace"
            state_dir = created / "state"
            staging_dir = created / "staging"
            source_workspace = loaded.workspace_root
            if source_workspace.is_symlink() or not source_workspace.is_dir():
                _fail(
                    "invalid_workspace",
                    source_workspace,
                    "source workspace must be a real directory",
                )
            self._copy_tree(source_workspace, workspace)
            _mkdir(state_dir)
            _mkdir(staging_dir)
            isolated = IsolatedEvalCase(
                workspace=workspace,
                state_dir=state_dir,
                staging_dir=staging_dir,
                source_manifest_hash=loaded.manifest_hash,
                case_root=created,
                temp_root=self.temp_root,
            )
        except Exception:
            if created.exists() and created not in before:
                shutil.rmtree(created, ignore_errors=True)
            raise
        return isolated

    def _copy_tree(self, source: Path, destination: Path) -> None:
        info = source.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            _fail("special_file", source, "workspace must not contain symlinks or special files")
        destination.mkdir(mode=_DIR_MODE)
        os.chmod(destination, _DIR_MODE)
        for entry in sorted(os.scandir(source), key=lambda item: item.name):
            src_child = Path(entry.path)
            dst_child = destination / entry.name
            child_info = entry.stat(follow_symlinks=False)
            mode = child_info.st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                _fail(
                    "special_file",
                    src_child,
                    "workspace must not contain symlinks or special files",
                )
            if stat.S_ISDIR(mode):
                self._copy_tree(src_child, dst_child)
            else:
                self._copy_file(src_child, dst_child)

    def _copy_file(self, source: Path, destination: Path) -> None:
        before = source.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            _fail("special_file", source, "workspace files must be regular files")
        data = source.read_bytes()
        after = source.lstat()
        if stat.S_ISLNK(after.st_mode) or not stat.S_ISREG(after.st_mode):
            _fail("special_file", source, "source file changed into a special file during copy")
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            _fail("copy_interrupted", source, "source file changed during copy")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(destination, flags, _FILE_MODE)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        dest_info = destination.lstat()
        if stat.S_ISLNK(dest_info.st_mode) or not stat.S_ISREG(dest_info.st_mode):
            _fail("special_file", destination, "copied file must remain a regular file")
        os.chmod(destination, _FILE_MODE)
