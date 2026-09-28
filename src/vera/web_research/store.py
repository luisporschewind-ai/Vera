"""Small private Run-local research state; never a public Event payload."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path

from pydantic import ValidationError

from vera.web_research.contracts import ResearchState


class ResearchStoreError(ValueError):
    pass


class ResearchStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def _path(self, run_id: str) -> Path:
        if re.fullmatch(r"run_[0-9a-f]{32}", run_id) is None:
            raise ResearchStoreError("invalid_run_id")
        return self.state_dir / "runs" / run_id / "web_research.json"

    def load(self, run_id: str) -> ResearchState:
        path = self._path(run_id)
        if not path.exists():
            return ResearchState()
        if path.is_symlink():
            raise ResearchStoreError("research_state_unsafe")
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(path, flags), "r", encoding="utf-8") as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise ResearchStoreError("research_state_unsafe")
                if os.name == "posix" and (
                    metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600
                ):
                    raise ResearchStoreError("research_state_unsafe")
                return ResearchState.model_validate_json(handle.read())
        except (OSError, UnicodeError, ValidationError) as exc:
            raise ResearchStoreError("research_state_unavailable") from exc

    def save(self, run_id: str, state: ResearchState) -> None:
        path = self._path(run_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(prefix=".web-research-", dir=path.parent)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(state.model_dump(mode="json"), handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except OSError as exc:
            raise ResearchStoreError("research_state_unavailable") from exc
