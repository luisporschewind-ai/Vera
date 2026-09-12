"""Bounded, one-shot evaluation failpoints. Not an OS sandbox."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from vera.contracts.recovery import RecoveryStage
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.recovery.models import RecoverySnapshot
from vera.workspace.apply import AtomicFileWriter, SimulatedCrash


class EvalFailpoint(StrEnum):
    AWAITING_CHANGESET_APPROVAL = "awaiting_changeset_approval"
    AFTER_FIRST_WRITE = "after_first_write"
    VERIFICATION_IN_FLIGHT = "verification_in_flight"
    VERIFYING_STABLE = "verifying_stable"


class EvalFailpointSnapshotStore(RecoverySnapshotStore):
    def __init__(
        self,
        state_dir: Path,
        failpoint: EvalFailpoint,
        on_trigger: Callable[[EvalFailpoint], None] | None = None,
    ) -> None:
        super().__init__(state_dir)
        self.failpoint = failpoint
        self._on_trigger = on_trigger
        self.triggered = False

    def save(self, snapshot: RecoverySnapshot) -> None:
        super().save(snapshot)
        if self.triggered:
            return
        if self._matches(snapshot):
            self.triggered = True
            if self._on_trigger is not None:
                self._on_trigger(self.failpoint)
            raise SimulatedCrash(self.failpoint.value)

    def _matches(self, snapshot: RecoverySnapshot) -> bool:
        if self.failpoint is EvalFailpoint.AWAITING_CHANGESET_APPROVAL:
            return snapshot.stage is RecoveryStage.AWAITING_CHANGESET_APPROVAL
        if self.failpoint is EvalFailpoint.VERIFYING_STABLE:
            return (
                snapshot.stage is RecoveryStage.VERIFYING
                and snapshot.verification_index == 0
                and not snapshot.verification_in_flight
            )
        if self.failpoint is EvalFailpoint.VERIFICATION_IN_FLIGHT:
            return bool(snapshot.verification_in_flight)
        return False


class EvalFailpointFileWriter(AtomicFileWriter):
    def __init__(self, on_trigger: Callable[[EvalFailpoint], None] | None = None) -> None:
        self._writes = 0
        self._on_trigger = on_trigger
        self.triggered = False

    def replace(self, path: Path, content: bytes, mode: int | None = None) -> None:
        self._writes += 1
        if self._writes >= 2:
            self.triggered = True
            if self._on_trigger is not None:
                self._on_trigger(EvalFailpoint.AFTER_FIRST_WRITE)
            raise SimulatedCrash(EvalFailpoint.AFTER_FIRST_WRITE.value)
        super().replace(path, content, mode)
