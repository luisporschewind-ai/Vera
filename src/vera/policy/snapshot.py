"""Effective policy snapshot and stable hash."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vera.policy.models import PolicyMode


def protected_roots_hash(globs: tuple[str, ...]) -> str:
    encoded = json.dumps(
        sorted(globs),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _EffectivePolicyFields(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_identity: str
    protected_path_globs: tuple[str, ...] = (
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_ed25519",
        "*.p12",
        "*.pfx",
    )
    user_allowed_command_prefixes: tuple[tuple[str, ...], ...] = ()
    project_denied_path_globs: tuple[str, ...] = ()
    project_denied_tools: tuple[str, ...] = ()


class EffectivePolicySnapshot(_EffectivePolicyFields):
    builtin_policy_version: Literal[1] = 1


class EffectivePolicySnapshotV2(_EffectivePolicyFields):
    builtin_policy_version: Literal[2] = 2
    policy_mode: PolicyMode = PolicyMode.BALANCED

    @property
    def protected_roots_hash(self) -> str:
        return protected_roots_hash(self.protected_path_globs)


def policy_hash(snapshot: EffectivePolicySnapshot | EffectivePolicySnapshotV2) -> str:
    encoded = json.dumps(
        snapshot.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_prefixes(
    prefixes: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(prefixes, key=lambda item: (len(item), item)))
