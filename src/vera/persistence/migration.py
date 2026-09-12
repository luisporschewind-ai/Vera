"""Non-destructive derived-state migration for run manifests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from vera.persistence.errors import StateVersionError, default_advice
from vera.persistence.run_manifest import RunManifest, RunManifestStore
from vera.persistence.run_store import RunFormatStatus, RunStore


class MigrationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    migration_id: str
    run_id: str
    from_status: RunFormatStatus
    to_journal_format_version: Literal[1] = 1
    migration_hash: str
    actions: tuple[str, ...] = ()


class MigrationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed", "failed", "noop"]
    migration_id: str
    run_id: str
    reason_code: str | None = None
    advice: str | None = None


class StateMigrationService:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.run_store = RunStore(state_dir)
        self.manifests = RunManifestStore(state_dir)

    def plan(self, run_id: str) -> MigrationPlan:
        status = self.run_store.format_status(run_id)
        if status is RunFormatStatus.MISSING:
            raise StateVersionError("missing_run")
        if status is RunFormatStatus.CORRUPT:
            raise StateVersionError("corrupt_run")
        if status is RunFormatStatus.UNSUPPORTED:
            raise StateVersionError("unsupported_version")
        actions: list[str] = []
        if status is RunFormatStatus.LEGACY:
            actions.append("write_manifest_v1")
        elif status is RunFormatStatus.CURRENT:
            actions.append("noop")
        payload = {
            "run_id": run_id,
            "from_status": status.value,
            "to_journal_format_version": 1,
            "actions": actions,
        }
        migration_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return MigrationPlan(
            migration_id=f"mig_{uuid4().hex}",
            run_id=run_id,
            from_status=status,
            migration_hash=migration_hash,
            actions=tuple(actions),
        )

    def apply(
        self,
        plan: MigrationPlan,
        *,
        replace: Callable[[Path, Path], None] | None = None,
    ) -> MigrationResult:
        try:
            current = self.plan(plan.run_id)
        except StateVersionError as exc:
            return MigrationResult(
                status="failed",
                migration_id=plan.migration_id,
                run_id=plan.run_id,
                reason_code=exc.code,
                advice=exc.advice,
            )
        if current.migration_hash != plan.migration_hash or current.actions != plan.actions:
            return MigrationResult(
                status="failed",
                migration_id=plan.migration_id,
                run_id=plan.run_id,
                reason_code="migration_hash_mismatch",
                advice=default_advice("migration_apply_failed"),
            )
        if plan.actions == ("noop",) or plan.from_status is RunFormatStatus.CURRENT:
            return MigrationResult(
                status="noop",
                migration_id=plan.migration_id,
                run_id=plan.run_id,
                reason_code="already_current",
            )
        run_dir = self.state_dir / "runs" / plan.run_id
        events_path = run_dir / "events.jsonl"
        backup_dir = run_dir / "migration-backup" / plan.migration_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(backup_dir, 0o700)
        if events_path.is_file():
            shutil.copy2(events_path, backup_dir / "events.jsonl")
            with (backup_dir / "events.jsonl").open("rb") as handle:
                handle.flush()
                os.fsync(handle.fileno())
        try:
            store = (
                RunManifestStore(self.state_dir, replace=replace)
                if replace is not None
                else self.manifests
            )
            store.save(RunManifest(run_id=plan.run_id, created_at=datetime.now(UTC)))
            loaded = self.manifests.load(plan.run_id)
            if loaded.journal_format_version != 1 or loaded.run_id != plan.run_id:
                raise StateVersionError("invalid_manifest")
        except Exception:
            return MigrationResult(
                status="failed",
                migration_id=plan.migration_id,
                run_id=plan.run_id,
                reason_code="migration_apply_failed",
                advice=default_advice("migration_apply_failed"),
            )
        return MigrationResult(
            status="completed",
            migration_id=plan.migration_id,
            run_id=plan.run_id,
        )
