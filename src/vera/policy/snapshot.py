"""Effective policy snapshot and stable hash."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EffectivePolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    builtin_policy_version: Literal[1] = 1
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


def policy_hash(snapshot: EffectivePolicySnapshot) -> str:
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
