"""Commands accepted by VeraRuntime."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from vera.contracts import ContractModel, JsonValue
from vera.contracts.conversation import ConversationMessage


class StartRun(ContractModel):
    schema_version: Literal[1] = 1
    goal: str
    workspace_root: Path
    model_profile: str
    verification_overrides: dict[str, JsonValue] = Field(default_factory=dict)
    conversation: tuple[ConversationMessage, ...] = ()
    mode: Literal["agent", "compact"] = "agent"


class ResolveApproval(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str
    approval_id: str
    target_hash: str
    decision: Literal["approve", "reject"]


class CancelRun(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str


class RollbackRun(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str | None = None
    checkpoint_id: str | None = None

    @model_validator(mode="after")
    def require_one_target(self) -> "RollbackRun":
        if (self.run_id is None) == (self.checkpoint_id is None):
            raise ValueError("exactly one of run_id or checkpoint_id is required")
        return self


class InspectRecovery(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str | None = None


class ResumeRun(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str


class AbandonRun(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str


type CoreCommand = (
    StartRun | ResolveApproval | CancelRun | RollbackRun | InspectRecovery | ResumeRun | AbandonRun
)
