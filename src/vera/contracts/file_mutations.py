"""Versioned contracts for one planned workspace file mutation."""

from pathlib import Path
from typing import Literal

from vera.contracts import ContractModel


class FileMutationPlan(ContractModel):
    schema_version: Literal[1] = 1
    action_id: str
    run_id: str
    operation: Literal["create", "replace", "edit"]
    path: str
    before_hash: str
    after_hash: str
    target_facts_hash: str
    unified_diff: str
    content_hash: str


class FileMutationCheckpoint(ContractModel):
    schema_version: Literal[1] = 1
    action_id: str
    run_id: str
    workspace_root: Path
    path: str
    before_exists: bool
    before_hash: str
    before_content_b64: str
    before_mode: int | None = None
    after_hash: str
