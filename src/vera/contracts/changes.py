"""Change Set contracts."""

from typing import Literal

from vera.contracts import ContractModel
from vera.contracts.verification import VerificationCommand


class FileChange(ContractModel):
    schema_version: Literal[1] = 1
    operation: Literal["create", "update", "delete"]
    path: str
    before_hash: str
    after_hash: str
    unified_diff: str


class ChangeSet(ContractModel):
    schema_version: Literal[1] = 1
    changeset_id: str
    run_id: str
    summary: str
    files: tuple[FileChange, ...]
    verification: tuple[VerificationCommand, ...]
    content_hash: str
