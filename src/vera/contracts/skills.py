"""Public contracts for the Core-native Skills control plane."""

from typing import Literal

from vera.contracts import ContractModel

SkillSourceKind = Literal["builtin", "user", "workspace"]
SkillTrustLevel = Literal["advisory", "untrusted"]
SkillAvailability = Literal["available", "conflict", "invalid", "incompatible"]
SkillSelectionMode = Literal["none", "explicit"]
SkillSelectionStatus = Literal["none", "selected", "invalid"]


class SkillSummary(ContractModel):
    schema_version: Literal[1] = 1
    skill_id: str | None = None
    name: str | None = None
    version: str | None = None
    description: str | None = None
    source_kind: SkillSourceKind
    trust_level: SkillTrustLevel
    availability: SkillAvailability
    manifest_hash: str | None = None
    resource_hash: str | None = None
    reason_codes: tuple[str, ...] = ()


class SkillSelection(ContractModel):
    schema_version: Literal[1] = 1
    mode: SkillSelectionMode = "none"
    selector: str | None = None
    status: SkillSelectionStatus = "none"
    skill_id: str | None = None
    source_kind: SkillSourceKind | None = None
    version: str | None = None
    manifest_hash: str | None = None
    reason_codes: tuple[str, ...] = ()


class SkillSnapshot(ContractModel):
    schema_version: Literal[1] = 1
    snapshot_id: str
    skill_id: str
    name: str
    version: str
    source_kind: SkillSourceKind
    manifest_hash: str
    package_hash: str
    resource_hash: str


class SkillSelectionChangedPayload(ContractModel):
    schema_version: Literal[1] = 1
    selection: SkillSelection


class SkillSnapshotBoundPayload(ContractModel):
    schema_version: Literal[1] = 1
    snapshot: SkillSnapshot
