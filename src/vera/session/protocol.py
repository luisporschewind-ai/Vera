"""NDJSON session protocol codecs for vera --json."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import StreamFrame
from vera.session.actions import (
    CancelActiveRun,
    CloseSession,
    ExecuteSlashCommand,
    ResolveSessionApproval,
    SessionAction,
    SubmitPrompt,
)


class SessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    record_type: Literal["event", "stream"]
    event: EventEnvelope | None = None
    stream: StreamFrame | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.record_type == "event":
            if self.event is None or self.stream is not None:
                raise ValueError("event record requires event only")
        elif self.stream is None or self.event is not None:
            raise ValueError("stream record requires stream only")
        return self


class SessionActionCodec:
    @staticmethod
    def decode(line: str) -> SessionAction:
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("session action must be an object")
        schema = payload.get("schema_version", 1)
        if schema != 1:
            raise ValueError(f"unsupported schema_version: {schema}")
        action_type = payload.get("type")
        body = {key: value for key, value in payload.items() if key != "schema_version"}
        match action_type:
            case "prompt.submit":
                return SubmitPrompt.model_validate(body)
            case "session.command":
                return ExecuteSlashCommand.model_validate(body)
            case "approval.resolve":
                return ResolveSessionApproval.model_validate(body)
            case "run.cancel":
                return CancelActiveRun.model_validate(body)
            case "session.close":
                return CloseSession.model_validate(body)
            case _:
                raise ValueError(f"unknown session action type: {action_type}")


class SessionRecordCodec:
    @staticmethod
    def encode(record: SessionRecord) -> str:
        return record.model_dump_json()

    @staticmethod
    def from_output(output: EventEnvelope | StreamFrame) -> SessionRecord:
        if isinstance(output, StreamFrame):
            return SessionRecord(record_type="stream", stream=output)
        return SessionRecord(record_type="event", event=output)


def input_failed_event(message: str, *, reason_code: str = "invalid_input") -> EventEnvelope:
    return EventEnvelope(
        event_id=f"session_{uuid4().hex}",
        run_id="session",
        sequence=1,
        timestamp=datetime.now(UTC),
        type="session.input_failed",
        payload={"reason_code": reason_code, "message": message},
    )


def encode_action(action: SessionAction) -> str:
    payload = action.model_dump(mode="json")
    payload["schema_version"] = 1
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
