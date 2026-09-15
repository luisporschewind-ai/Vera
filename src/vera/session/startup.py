"""Resolve CLI session open requests through ConversationSessionStore."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vera.persistence.errors import JournalCorrupt, PersistenceFault, StateVersionError
from vera.persistence.session_store import ConversationSessionStore, LoadedConversationSession

SessionOpenMode = Literal["new", "continue", "resume_picker", "resume_id"]
HISTORY_DISPLAY_LIMIT = 40


class SessionOpenRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: SessionOpenMode
    session_id: str | None = None


class SessionStartupError(Exception):
    def __init__(self, code: str, message: str, *, advice: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.advice = advice or message


class SessionStartupService:
    def __init__(self, store: ConversationSessionStore) -> None:
        self.store = store

    def resolve(
        self,
        request: SessionOpenRequest,
        workspace: Path,
        *,
        interactive_tty: bool,
    ) -> LoadedConversationSession:
        try:
            return self._resolve(request, workspace, interactive_tty=interactive_tty)
        except SessionStartupError:
            raise
        except (JournalCorrupt, StateVersionError, PersistenceFault) as exc:
            raise SessionStartupError(exc.code, str(exc), advice=exc.advice) from exc

    def _resolve(
        self,
        request: SessionOpenRequest,
        workspace: Path,
        *,
        interactive_tty: bool,
    ) -> LoadedConversationSession:
        if request.mode == "new":
            return self.store.create(workspace)
        if request.mode == "continue":
            loaded = self.store.latest_for_workspace(workspace)
            if loaded is None:
                raise SessionStartupError(
                    "no_matching_session",
                    "当前工作区没有可继续的会话",
                    advice="使用 vera 新建，或 vera -r <session-id> 明确恢复。",
                )
            return loaded
        if request.mode == "resume_id":
            if not request.session_id:
                raise SessionStartupError("invalid_session_id", "恢复会话需要明确的 session id")
            return self.store.load(request.session_id, workspace)
        if not interactive_tty:
            raise SessionStartupError(
                "picker_requires_id",
                "非交互环境不能打开会话选择器",
                advice="请传入 vera -r <session-id>。",
            )
        raise SessionStartupError(
            "picker_required",
            "需要交互选择会话",
            advice="在 TTY 中选择，或传入明确 session id。",
        )

    def source_for(self, request: SessionOpenRequest) -> Literal["new", "continued", "resumed"]:
        if request.mode == "continue":
            return "continued"
        if request.mode in {"resume_id", "resume_picker"}:
            return "resumed"
        return "new"
