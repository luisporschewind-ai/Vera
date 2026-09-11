"""Atomic, private recovery snapshot persistence."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

from vera.persistence.errors import StateVersionError
from vera.persistence.snapshot_codec import SnapshotCodec
from vera.recovery.models import RecoverySnapshot

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def is_safe_run_id(run_id: str) -> bool:
    return Path(run_id).name == run_id and _SAFE_RUN_ID.fullmatch(run_id) is not None


class RecoverySnapshotError(ValueError):
    """Raised when a recovery snapshot cannot be written or read safely."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RecoverySnapshotStore:
    def __init__(
        self,
        state_dir: Path,
        replace: Callable[[Path, Path], None] = os.replace,
        fsync: Callable[[int], None] = os.fsync,
        codec: SnapshotCodec | None = None,
    ) -> None:
        self.state_dir = state_dir
        self._replace = replace
        self._fsync = fsync
        self._codec = codec or SnapshotCodec()

    def exists(self, run_id: str) -> bool:
        self._assert_safe_run_id(run_id)
        return self._path(run_id).is_file()

    def load(self, run_id: str) -> RecoverySnapshot:
        self._assert_safe_run_id(run_id)
        path = self._path(run_id)
        if not path.is_file():
            raise RecoverySnapshotError("missing_snapshot")
        try:
            return self._codec.decode(path.read_bytes())
        except StateVersionError as exc:
            raise RecoverySnapshotError(exc.code) from exc
        except RecoverySnapshotError:
            raise
        except Exception as exc:
            raise RecoverySnapshotError("invalid_snapshot") from exc

    def save(self, snapshot: RecoverySnapshot) -> None:
        self._assert_safe_run_id(snapshot.run_id)
        directory = self._run_dir(snapshot.run_id)
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        target = directory / "recovery.json"
        temporary = directory / "recovery.json.tmp"
        payload = self._codec.encode(snapshot)
        try:
            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                self._fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            self._replace(temporary, target)
            os.chmod(target, 0o600)
        except RecoverySnapshotError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise RecoverySnapshotError("snapshot_write_failed") from exc

    def _run_dir(self, run_id: str) -> Path:
        return self.state_dir / "runs" / run_id

    def _path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "recovery.json"

    @staticmethod
    def _assert_safe_run_id(run_id: str) -> None:
        if not is_safe_run_id(run_id):
            raise RecoverySnapshotError("invalid_run_id")
