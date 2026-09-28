"""Versioned facts for one prepared tool action."""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Literal, NoReturn, Self

from pydantic import Field, field_validator, model_validator

from vera.contracts import ContractModel, JsonValue


class ToolEffect(StrEnum):
    WORKSPACE_READ = "workspace_read"
    WORKSPACE_WRITE = "workspace_write"
    PROCESS_EXECUTE = "process_execute"
    NETWORK_ACCESS = "network_access"
    EXTERNAL_SERVICE = "external_service"
    SECRET_ACCESS = "secret_access"
    FILE_ACCESS_GRANT = "file_access_grant"
    APPLE_IOS_BUILD_SERVICES = "apple_ios_build_services"


class FrozenJsonDict(dict[str, JsonValue]):
    """A JSON object whose nested objects and arrays cannot be mutated."""

    def __init__(self, values: dict[str, JsonValue]) -> None:
        dict.__init__(self)
        for key, value in values.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            dict.__setitem__(self, key, _freeze_json(value))

    @staticmethod
    def _immutable(*_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("frozen JSON objects cannot be mutated")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def _freeze_json(value: JsonValue) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, dict):
        return FrozenJsonDict(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


class ToolRiskFacts(ContractModel):
    """Normalized facts Policy needs before it may classify a side effect."""

    normalized_paths: tuple[str, ...] = ()
    argv: tuple[str, ...] = ()
    cwd: str | None = None
    recoverable: bool = False
    destructive: bool = False
    outside_workspace: bool = False
    protected_target: bool = False
    external_target: str | None = None
    secrets_present: bool = False
    policy_forbidden: bool = False
    policy_reason_code: str | None = None
    facts_complete: bool = False
    target_facts_hash: str | None = None


class ToolAction(ContractModel):
    schema_version: Literal[1] = 1
    action_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_version: int = Field(gt=0)
    effects: tuple[ToolEffect, ...] = Field(min_length=1)
    workspace_identity: str = Field(min_length=1)
    normalized_arguments: dict[str, JsonValue]
    risk_facts: ToolRiskFacts = Field(default_factory=ToolRiskFacts)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("normalized_arguments", mode="after")
    @classmethod
    def freeze_arguments(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return FrozenJsonDict(value)

    @model_validator(mode="after")
    def input_hash_matches_facts(self) -> Self:
        expected = tool_action_input_hash(
            tool_name=self.tool_name,
            tool_version=self.tool_version,
            workspace_identity=self.workspace_identity,
            effects=self.effects,
            normalized_arguments=self.normalized_arguments,
            risk_facts=self.risk_facts,
        )
        if self.input_hash != expected:
            raise ValueError("input_hash does not match normalized tool action facts")
        return self


def tool_action_input_hash(
    *,
    tool_name: str,
    tool_version: int,
    workspace_identity: str,
    effects: tuple[ToolEffect, ...],
    normalized_arguments: dict[str, JsonValue],
    risk_facts: ToolRiskFacts | None = None,
) -> str:
    """Bind normalized execution inputs without action/run identity."""

    encoded = json.dumps(
        {
            "effects": [effect.value for effect in effects],
            "normalized_arguments": normalized_arguments,
            "risk_facts": (risk_facts or ToolRiskFacts()).model_dump(mode="json"),
            "tool_name": tool_name,
            "tool_version": tool_version,
            "workspace_identity": workspace_identity,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
