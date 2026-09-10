"""Checkpoint contracts for safe apply and rollback."""

from pathlib import Path
from typing import Literal

from vera.contracts import ContractModel


class CheckpointFile(ContractModel):
    schema_version: Literal[1] = 1
    existed: bool
    content_hash: str | None = None
    mode: int | None = None


class CheckpointManifest(ContractModel):
    schema_version: Literal[1] = 1
    checkpoint_id: str
    run_id: str
    workspace_root: Path
    before: dict[str, CheckpointFile]
    after_hashes: dict[str, str]
