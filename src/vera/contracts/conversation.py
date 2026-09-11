"""Conversation messages shared by StartRun and session context."""

from typing import Literal

from pydantic import Field

from vera.contracts import ContractModel


class ConversationMessage(ContractModel):
    schema_version: Literal[1] = 1
    role: Literal["user", "assistant", "summary"]
    content: str = Field(min_length=1)
