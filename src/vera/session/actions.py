"""UI-independent session actions shared by TUI, Plain, and JSON drivers."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SubmitPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["prompt.submit"] = "prompt.submit"
    text: str = Field(min_length=1)


class ExecuteSlashCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["session.command"] = "session.command"
    raw: str = Field(min_length=1)


class ResolveSessionApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["approval.resolve"] = "approval.resolve"
    approval_id: str = Field(min_length=1)
    decision: Literal["approve", "reject", "cancel"]


class CancelActiveRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["run.cancel"] = "run.cancel"
    run_id: str = Field(min_length=1)


class CloseSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["session.close"] = "session.close"


SessionAction = Annotated[
    SubmitPrompt | ExecuteSlashCommand | ResolveSessionApproval | CancelActiveRun | CloseSession,
    Field(discriminator="type"),
]
