"""Per-run format manifest for journal and migration status."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.persistence.errors import StateVersionError
from vera.persistence.recovery_snapshot import is_safe_run_id


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: Literal[1] = 1
    journal_format_version: Literal[1] = 1
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunManifestStore:
    def __init__(
        self,
        state_dir: Path,
        *,
        replace: Callable[[Path, Path], None] = os.replace,
        fsync: Callable[[int], None] = os.fsync,
    ) -> None:
        self.state_dir = state_dir
        self._replace = replace
        self._fsync = fsync

    def path_for(self, run_id: str) -> Path:
        return self.state_dir / "runs" / run_id / "manifest.json"

    def exists(self, run_id: str) -> bool:
        self._assert_safe(run_id)
        return self.path_for(run_id).is_file()

    def load(self, run_id: str) -> RunManifest:
        self._assert_safe(run_id)
        path = self.path_for(run_id)
        if not path.is_file():
            raise StateVersionError("missing_manifest")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateVersionError("invalid_manifest") from exc
        if not isinstance(payload, dict) or "manifest_version" not in payload:
            raise StateVersionError("missing_version")
        version = payload["manifest_version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise StateVersionError("invalid_manifest")
        if version != 1:
            raise StateVersionError("unsupported_version", version)
        try:
            manifest = RunManifest.model_validate(payload)
        except Exception as exc:
            raise StateVersionError("invalid_manifest", version) from exc
        if manifest.run_id != run_id:
            raise StateVersionError("manifest_run_id_mismatch", version)
        if manifest.journal_format_version != 1:
            raise StateVersionError("unsupported_version", manifest.journal_format_version)
        return manifest

    def save(self, manifest: RunManifest) -> None:
        self._assert_safe(manifest.run_id)
        directory = self.state_dir / "runs" / manifest.run_id
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        target = self.path_for(manifest.run_id)
        temporary = directory / "manifest.json.tmp"
        payload = json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                self._fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            self._replace(temporary, target)
            os.chmod(target, 0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _assert_safe(run_id: str) -> None:
        if not is_safe_run_id(run_id):
            raise StateVersionError("invalid_run_id")
