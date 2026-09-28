"""User-owned sandbox runtime settings, never loaded from a project."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from pathlib import Path

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict

from vera.process.supervisor import ProcessRequest
from vera.sandbox.access import FilePermissions
from vera.sandbox.backend import SandboxError, SrtBackend
from vera.sandbox.supervision import SandboxBackend


class SandboxSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    runtime_root: Path
    node: Path
    base_readable: tuple[Path, ...]
    git_executable: Path | None = None
    developer_dir: Path | None = None
    directory_listable: tuple[Path, ...] = ()


class UnavailableBackend:
    def prepare(
        self, request: ProcessRequest, permissions: FilePermissions
    ) -> AbstractContextManager[ProcessRequest]:
        raise SandboxError("sandbox_setup_required")


def settings_path() -> Path:
    return user_config_path("Vera") / "sandbox.json"


def load_backend() -> SandboxBackend:
    path = settings_path()
    if not path.exists():
        return UnavailableBackend()
    try:
        config = SandboxSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise SandboxError("sandbox_invalid_settings") from exc
    return SrtBackend(
        runtime_root=config.runtime_root,
        node=config.node,
        base_readable=config.base_readable,
        git_executable=config.git_executable,
        developer_dir=config.developer_dir,
        directory_listable=config.directory_listable,
    )
