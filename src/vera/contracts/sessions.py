"""Versioned conversation session journal records.

These models are independent of `vera.session.protocol.SessionRecord`, which
belongs to the JSON client wire protocol.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from vera.contracts import ContractModel
from vera.contracts.skills import SkillSelection

SessionRecordType = Literal[
    "session.created",
    "skill.selection.changed",
    "turn.committed",
    "context.compacted",
    "session.renamed",
    "session.closed",
]

TerminalState = Literal["completed", "failed", "cancelled", "recovery", "response"]


def _required_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("text must not be blank")
    return text


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class ConversationTurn(ContractModel):
    user_text: str
    assistant_text: str
    run_id: str | None
    terminal_state: TerminalState

    @field_validator("user_text", "assistant_text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("run_id")
    @classmethod
    def run_id_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _required_text(value)


class SessionCreatedPayload(ContractModel):
    type: Literal["session.created"] = "session.created"
    workspace_identity: str
    workspace_root: str
    created_at: datetime
    repaired_from_session_id: str | None = None
    repaired_through_sequence: int | None = Field(default=None, ge=1)
    source_digest: str | None = None

    @field_validator("workspace_identity")
    @classmethod
    def identity_not_blank(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("workspace_root")
    @classmethod
    def root_must_be_absolute(cls, value: str) -> str:
        text = _required_text(value)
        if not Path(text).is_absolute():
            raise ValueError("workspace_root must be absolute")
        return text

    @field_validator("created_at")
    @classmethod
    def created_at_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("repaired_from_session_id", "source_digest")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _required_text(value)


class TurnCommittedPayload(ContractModel):
    type: Literal["turn.committed"] = "turn.committed"
    turn: ConversationTurn


class SkillSelectionChangedSessionPayload(ContractModel):
    type: Literal["skill.selection.changed"] = "skill.selection.changed"
    selection: SkillSelection


class ContextCompactedPayload(ContractModel):
    type: Literal["context.compacted"] = "context.compacted"
    summary: str
    through_sequence: int = Field(ge=1)
    compact_count: int = Field(ge=1)

    @field_validator("summary")
    @classmethod
    def summary_not_blank(cls, value: str) -> str:
        return _required_text(value)


class SessionRenamedPayload(ContractModel):
    type: Literal["session.renamed"] = "session.renamed"
    title: str

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        return _required_text(value)


class SessionClosedPayload(ContractModel):
    type: Literal["session.closed"] = "session.closed"


SessionPayload = Annotated[
    SessionCreatedPayload
    | SkillSelectionChangedSessionPayload
    | TurnCommittedPayload
    | ContextCompactedPayload
    | SessionRenamedPayload
    | SessionClosedPayload,
    Field(discriminator="type"),
]


class ConversationSessionRecord(ContractModel):
    session_format_version: Literal[1] = 1
    record_id: str
    session_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime
    type: SessionRecordType
    payload: SessionPayload

    @field_validator("record_id", "session_id")
    @classmethod
    def ids_not_blank(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("timestamp")
    @classmethod
    def timestamp_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def payload_matches_type(self) -> ConversationSessionRecord:
        if self.payload.type != self.type:
            raise ValueError("payload type must match record type")
        return self
