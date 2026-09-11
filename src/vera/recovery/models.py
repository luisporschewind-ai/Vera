"""Private, versioned recovery snapshot models."""

from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vera.contracts.approvals import ApprovalRequest
from vera.contracts.changes import ChangeSet
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryPlan, RecoveryStage
from vera.workspace.changeset import BuiltChangeSet


class FrozenPrivateModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("invalid intended content encoding") from exc


class PersistedChangeSet(FrozenPrivateModel):
    change_set: ChangeSet
    intended_content_b64: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def encode_bytes(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @classmethod
    def from_built(cls, built: BuiltChangeSet) -> PersistedChangeSet:
        return cls(
            change_set=built.change_set,
            intended_content_b64={
                path: cls.encode_bytes(payload) for path, payload in built.intended_bytes.items()
            },
        )

    def decoded_content(self) -> dict[str, bytes]:
        return {path: _strict_b64decode(blob) for path, blob in self.intended_content_b64.items()}

    def to_built(self) -> BuiltChangeSet:
        return BuiltChangeSet(change_set=self.change_set, intended_bytes=self.decoded_content())

    @model_validator(mode="after")
    def verify_intended_content(self) -> Self:
        contents = self.decoded_content()
        for item in self.change_set.files:
            if item.operation == "delete":
                if item.path in contents:
                    raise ValueError(f"delete must not include content: {item.path}")
                continue
            payload = contents.get(item.path)
            if payload is None:
                raise ValueError(f"missing intended content: {item.path}")
            if _sha256_bytes(payload) != item.after_hash:
                raise ValueError(f"after_hash mismatch: {item.path}")
        extra = set(contents) - {item.path for item in self.change_set.files}
        if extra:
            raise ValueError(f"unexpected intended content: {sorted(extra)[0]}")
        return self


class RecoverySnapshot(FrozenPrivateModel):
    snapshot_version: Literal[1] = 1
    run_id: str
    workspace_root: Path
    workspace_identity: str
    command: StartRun
    stage: RecoveryStage
    last_event_sequence: int
    built_changeset: PersistedChangeSet | None = None
    checkpoint_id: str | None = None
    pending_approval: ApprovalRequest | None = None
    verification_index: int = 0
    verification_failed: bool = False
    verification_in_flight: bool = False
    workspace_write_started: bool = False
    recovery_plan: RecoveryPlan | None = None
    created_at: datetime
    updated_at: datetime
    vera_version: str
