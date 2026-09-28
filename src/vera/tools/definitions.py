"""Shared tool metadata and result contracts."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from vera.contracts import ContractModel, JsonValue
from vera.contracts.tool_actions import ToolEffect


class ToolDefinition(ContractModel):
    schema_version: Literal[1] = 1
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class ToolDefinitionV2(ContractModel):
    schema_version: Literal[2] = 2
    name: str
    description: str
    input_schema: dict[str, JsonValue]
    tool_version: int = Field(gt=0)
    effects: tuple[ToolEffect, ...]
    supports_cancellation: bool
    supports_recovery: bool
    max_output_bytes: int = Field(gt=0)


type ToolDefinitionAny = Annotated[
    ToolDefinition | ToolDefinitionV2,
    Field(discriminator="schema_version"),
]

_TOOL_DEFINITION_ADAPTER: TypeAdapter[ToolDefinitionAny] = TypeAdapter(ToolDefinitionAny)


def decode_tool_definition(payload: JsonValue) -> ToolDefinitionAny:
    return _TOOL_DEFINITION_ADAPTER.validate_python(payload)


class ToolResult(ContractModel):
    schema_version: Literal[1] = 1
    ok: bool
    content: JsonValue = None
    truncated: bool = False
    error_code: str | None = None
