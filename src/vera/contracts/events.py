"""Ordered Runtime events."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from vera.contracts import ContractModel, JsonValue


class EventEnvelope(ContractModel):
    schema_version: Literal[1] = 1
    event_id: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime
    type: str
    payload: dict[str, JsonValue]
