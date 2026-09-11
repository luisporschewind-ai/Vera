"""Versioned encode/decode for public Core commands and events."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from vera.contracts.commands import (
    AbandonRun,
    ApplyStateMigration,
    CancelRun,
    CoreCommand,
    InspectRecovery,
    InspectState,
    PlanStateMigration,
    ResolveApproval,
    ResumeRun,
    RollbackRun,
    StartRun,
)
from vera.contracts.events import EventEnvelope


class CommandType(StrEnum):
    START_RUN = "start_run"
    RESOLVE_APPROVAL = "resolve_approval"
    CANCEL_RUN = "cancel_run"
    ROLLBACK_RUN = "rollback_run"
    INSPECT_RECOVERY = "inspect_recovery"
    RESUME_RUN = "resume_run"
    ABANDON_RUN = "abandon_run"
    INSPECT_STATE = "inspect_state"
    PLAN_STATE_MIGRATION = "plan_state_migration"
    APPLY_STATE_MIGRATION = "apply_state_migration"


class ContractVersionError(ValueError):
    """Raised when a contract payload uses an unsupported schema version."""

    def __init__(self, code: str, version: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.version = version


_COMMAND_DECODERS: dict[tuple[CommandType, int], type[Any]] = {
    (CommandType.START_RUN, 1): StartRun,
    (CommandType.RESOLVE_APPROVAL, 1): ResolveApproval,
    (CommandType.CANCEL_RUN, 1): CancelRun,
    (CommandType.ROLLBACK_RUN, 1): RollbackRun,
    (CommandType.INSPECT_RECOVERY, 1): InspectRecovery,
    (CommandType.RESUME_RUN, 1): ResumeRun,
    (CommandType.ABANDON_RUN, 1): AbandonRun,
    (CommandType.INSPECT_STATE, 1): InspectState,
    (CommandType.PLAN_STATE_MIGRATION, 1): PlanStateMigration,
    (CommandType.APPLY_STATE_MIGRATION, 1): ApplyStateMigration,
}

_COMMAND_TYPES: dict[type[Any], CommandType] = {
    StartRun: CommandType.START_RUN,
    ResolveApproval: CommandType.RESOLVE_APPROVAL,
    CancelRun: CommandType.CANCEL_RUN,
    RollbackRun: CommandType.ROLLBACK_RUN,
    InspectRecovery: CommandType.INSPECT_RECOVERY,
    ResumeRun: CommandType.RESUME_RUN,
    AbandonRun: CommandType.ABANDON_RUN,
    InspectState: CommandType.INSPECT_STATE,
    PlanStateMigration: CommandType.PLAN_STATE_MIGRATION,
    ApplyStateMigration: CommandType.APPLY_STATE_MIGRATION,
}


class ContractCodec:
    def encode_command(self, command: CoreCommand) -> bytes:
        return command.model_dump_json().encode("utf-8")

    def decode_command(self, command_type: CommandType, data: bytes) -> CoreCommand:
        version = self._read_schema_version(data)
        decoder = _COMMAND_DECODERS.get((command_type, version))
        if decoder is None:
            raise ContractVersionError("unsupported_version", version)
        try:
            return decoder.model_validate_json(data)  # type: ignore[no-any-return]
        except ContractVersionError:
            raise
        except Exception as exc:
            raise ContractVersionError("invalid_contract", version) from exc

    def encode_event(self, event: EventEnvelope) -> bytes:
        return event.model_dump_json().encode("utf-8")

    def decode_event(self, data: bytes) -> EventEnvelope:
        version = self._read_schema_version(data)
        if version != 1:
            raise ContractVersionError("unsupported_version", version)
        try:
            return EventEnvelope.model_validate_json(data)
        except ContractVersionError:
            raise
        except Exception as exc:
            raise ContractVersionError("invalid_contract", version) from exc

    def command_type_for(self, command: CoreCommand) -> CommandType:
        return _COMMAND_TYPES[type(command)]

    @staticmethod
    def _read_schema_version(data: bytes) -> int:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractVersionError("invalid_contract") from exc
        if not isinstance(payload, dict) or "schema_version" not in payload:
            raise ContractVersionError("missing_version")
        version = payload["schema_version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise ContractVersionError("invalid_contract")
        return version
