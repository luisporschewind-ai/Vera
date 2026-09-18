"""Read-only compatibility manifest for public Core client contracts."""

from __future__ import annotations

import json
from typing import Literal

from vera.contracts import ContractModel
from vera.contracts.changes import ChangeSet
from vera.contracts.codec import _COMMAND_DECODERS, CommandType
from vera.contracts.errors import CoreErrorCode
from vera.contracts.events import EventEnvelope
from vera.contracts.recovery import RecoveryClassification
from vera.contracts.tool_actions import ToolAction
from vera.policy.models import PolicyAction
from vera.policy.permissions import WorkspacePermissionSummary
from vera.runtime.approval import ApprovalKind
from vera.session.actions import (
    CancelActiveRun,
    ClearQueuedPrompt,
    CloseSession,
    ConfirmExternalEditor,
    ExecuteSlashCommand,
    OpenExternalEditor,
    QueuePrompt,
    ResolveSessionApproval,
    SubmitPrompt,
)
from vera.tools.definitions import ToolDefinition, ToolDefinitionV2

CURRENT_PROTOCOL_VERSION = 1

COMPATIBILITY_RULES: dict[str, str] = {
    "additive": (
        "New optional fields, event types, or command names may be added at the "
        "current schema_version. Existing clients may ignore unknown additive data. "
        "StartRun.mode=project_init and project.instructions.loaded/skipped/status "
        "are additive at schema_version 1; default mode remains agent. ToolDefinition v2, "
        "ToolAction, and public permission summaries are additive tooling contracts."
    ),
    "deprecated": (
        "Deprecated fields remain readable at the current schema_version but must "
        "not become newly required. Removal requires a breaking change."
    ),
    "breaking": (
        "Renaming or removing a required field, changing a field meaning, or "
        "dropping a decoder is breaking and requires a new schema_version plus "
        "an explicit decoder. Human terminal chrome and presenter classes are "
        "not public contracts."
    ),
}

_SESSION_ACTIONS = (
    SubmitPrompt,
    ExecuteSlashCommand,
    ResolveSessionApproval,
    CancelActiveRun,
    CloseSession,
    QueuePrompt,
    ClearQueuedPrompt,
    ConfirmExternalEditor,
    OpenExternalEditor,
)


class NamedContract(ContractModel):
    name: str
    schema_version: int
    required_fields: tuple[str, ...]


class CompatibilityManifest(ContractModel):
    schema_version: Literal[1] = 1
    protocol_version: int = CURRENT_PROTOCOL_VERSION
    commands: tuple[NamedContract, ...]
    event_envelope: NamedContract
    runtime_output: tuple[str, ...]
    error_codes: tuple[str, ...]
    approval_kinds: tuple[str, ...]
    recovery_classifications: tuple[str, ...]
    session_records: tuple[NamedContract, ...]
    session_actions: tuple[NamedContract, ...]
    tooling_contracts: tuple[NamedContract, ...] = ()
    compatibility_rules: dict[str, str]


def required_fields_for(model: type[ContractModel] | type[object]) -> tuple[str, ...]:
    fields = getattr(model, "model_fields", {})
    names = [name for name, info in fields.items() if info.is_required()]
    return tuple(sorted(names))


def current_compatibility_manifest() -> CompatibilityManifest:
    commands = []
    for command_type in CommandType:
        decoder = _COMMAND_DECODERS[(command_type, 1)]
        commands.append(
            NamedContract(
                name=command_type.value,
                schema_version=1,
                required_fields=required_fields_for(decoder),
            )
        )
    session_records = (
        NamedContract(
            name="event",
            schema_version=1,
            required_fields=("event", "record_type", "schema_version"),
        ),
        NamedContract(
            name="stream",
            schema_version=1,
            required_fields=("record_type", "schema_version", "stream"),
        ),
    )
    session_actions = tuple(
        NamedContract(
            name=str(model.model_fields["type"].default),
            schema_version=1,
            required_fields=required_fields_for(model),
        )
        for model in _SESSION_ACTIONS
    )
    tooling_contracts = tuple(
        NamedContract(
            name=model.__name__,
            schema_version=version,
            required_fields=required_fields_for(model),
        )
        for model, version in (
            (ToolDefinition, 1),
            (ToolDefinitionV2, 2),
            (ToolAction, 1),
            (WorkspacePermissionSummary, 1),
            (PolicyAction, 1),
            (ChangeSet, 1),
        )
    )
    return CompatibilityManifest(
        commands=tuple(commands),
        event_envelope=NamedContract(
            name="event_envelope",
            schema_version=1,
            required_fields=required_fields_for(EventEnvelope),
        ),
        runtime_output=("event", "stream"),
        error_codes=tuple(sorted(item.value for item in CoreErrorCode)),
        approval_kinds=tuple(sorted(item.value for item in ApprovalKind)),
        recovery_classifications=tuple(sorted(item.value for item in RecoveryClassification)),
        session_records=session_records,
        session_actions=session_actions,
        tooling_contracts=tooling_contracts,
        compatibility_rules=dict(COMPATIBILITY_RULES),
    )


def encode_compatibility_manifest(manifest: CompatibilityManifest) -> str:
    payload = manifest.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
