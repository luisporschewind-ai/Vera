"""Shared tool metadata and result contracts."""

from typing import Literal

from vera.contracts import ContractModel, JsonValue


class ToolDefinition(ContractModel):
    schema_version: Literal[1] = 1
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class ToolResult(ContractModel):
    schema_version: Literal[1] = 1
    ok: bool
    content: JsonValue = None
    truncated: bool = False
    error_code: str | None = None
