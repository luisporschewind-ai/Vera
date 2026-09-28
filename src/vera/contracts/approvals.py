"""Approval requests emitted by VeraRuntime."""

from typing import Literal, Self

from pydantic import model_validator

from vera.content.envelope import ContentEnvelope
from vera.contracts import ContractModel
from vera.sandbox.apple_services import APPLE_IOS_BUILD_SERVICES


class ApprovalRequest(ContractModel):
    schema_version: Literal[1] = 1
    approval_id: str
    run_id: str
    kind: Literal["changeset", "command", "tool", "recovery"]
    target_id: str
    target_hash: str
    description: str
    risk: Literal["low", "medium", "high"]
    workspace_identity: str | None = None
    policy_hash: str | None = None
    fact_hash: str | None = None
    security_context_hash: str | None = None
    required_capabilities: tuple[Literal["apple_ios_build_services"], ...] = ()
    system_service_names: tuple[str, ...] = ()
    risk_labels: tuple[str, ...] = ()
    risk_sources: tuple[ContentEnvelope, ...] = ()
    available_scopes: tuple[Literal["once", "run", "workspace"], ...] = (
        "once",
        "run",
        "workspace",
    )

    @model_validator(mode="after")
    def apple_service_set_is_core_owned(self) -> Self:
        if self.required_capabilities == ("apple_ios_build_services",):
            if self.available_scopes != ("once",):
                raise ValueError("Apple build services are once-only")
            if self.system_service_names != APPLE_IOS_BUILD_SERVICES:
                raise ValueError("Apple build service set must match the Core-owned names")
        elif self.required_capabilities or self.system_service_names:
            raise ValueError("unsupported system capability")
        return self
