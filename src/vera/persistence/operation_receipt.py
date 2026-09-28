"""Idempotent operation receipts for resume, approval, cancel, and rollback."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.contracts.errors import classify_os_error
from vera.persistence.decode import inspect_payload, parse_json_object
from vera.persistence.errors import PersistenceFault, StateVersionError
from vera.persistence.recovery_snapshot import is_safe_run_id

_RECEIPT_ALLOWED = frozenset(
    {
        "receipt_version",
        "operation_id",
        "operation",
        "run_id",
        "input_hash",
        "terminal_result",
        "effect_refs",
        "facts",
        "created_at",
    }
)
_RECEIPT_REQUIRED = frozenset(
    {
        "receipt_version",
        "operation_id",
        "operation",
        "run_id",
        "input_hash",
        "terminal_result",
    }
)


class OperationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_version: Literal[1] = 1
    operation_id: str
    operation: Literal[
        "resume",
        "resolve_approval",
        "cancel",
        "rollback",
        "file_mutation",
        "process",
        "git_commit",
        "git_branch",
    ]
    run_id: str
    input_hash: str
    terminal_result: str
    effect_refs: tuple[str, ...] = ()
    facts: dict[str, str] = Field(default_factory=dict)
    created_at: datetime


def receipt_key(operation: str, payload: dict[str, Any]) -> tuple[str, str]:
    blob = json.dumps(
        {"operation": operation, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    return f"{operation}_{digest[:16]}", digest


class OperationReceiptStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def path_for(self, run_id: str, operation_id: str) -> Path:
        return self.state_dir / "runs" / run_id / "operations" / f"{operation_id}.json"

    def load(self, run_id: str, operation_id: str) -> OperationReceipt | None:
        self._assert_safe(run_id)
        path = self.path_for(run_id, operation_id)
        if not path.is_file():
            return None
        payload = parse_json_object(path.read_bytes())
        inspect_payload(
            payload,
            allowed_keys=_RECEIPT_ALLOWED,
            required_keys=_RECEIPT_REQUIRED,
            version_key="receipt_version",
            supported_versions=frozenset({1}),
        )
        return OperationReceipt.model_validate(payload)

    def save(self, receipt: OperationReceipt) -> None:
        self._assert_safe(receipt.run_id)
        path = self.path_for(receipt.run_id, receipt.operation_id)
        if path.is_file():
            existing = self.load(receipt.run_id, receipt.operation_id)
            if existing is not None and existing.input_hash == receipt.input_hash:
                return
            raise PersistenceFault("checksum_mismatch", "operation receipt conflict")
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        temporary = directory / f"{receipt.operation_id}.json.tmp"
        body = json.dumps(
            receipt.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise PersistenceFault(classify_os_error(exc), str(exc)) from exc
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _assert_safe(run_id: str) -> None:
        if not is_safe_run_id(run_id):
            raise StateVersionError("invalid_run_id")
