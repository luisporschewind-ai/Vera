"""Reload a classified run into a paused RunContext."""

from __future__ import annotations

from vera.contracts.recovery import RecoveryClassification, RecoveryReport
from vera.persistence.journal import EventJournal
from vera.recovery.coordinator import RecoveryCoordinator
from vera.recovery.hydrator import RecoveryHydrator
from vera.redaction import Redactor
from vera.runtime.context import RunContext

_RESUMABLE = frozenset(
    {
        RecoveryClassification.RESUMABLE_APPROVAL,
        RecoveryClassification.RESUMABLE_VERIFICATION,
        RecoveryClassification.RECOVERABLE_PARTIAL_APPLY,
    }
)


class ResumeRejected(ValueError):
    """Raised when a run is classified but must not be rehydrated."""

    def __init__(self, report: RecoveryReport) -> None:
        self.report = report
        super().__init__(report.reason_code)


class RunResumer:
    def __init__(
        self,
        coordinator: RecoveryCoordinator,
        *,
        hydrator: RecoveryHydrator | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.hydrator = hydrator or RecoveryHydrator()

    def load_context(self, run_id: str) -> RunContext:
        report = self.coordinator.prepare_resume(run_id)
        if report.classification not in _RESUMABLE:
            raise ResumeRejected(report)
        snapshot = self.coordinator.snapshot_store.load(run_id)
        journal = EventJournal(self.coordinator.state_dir, run_id, Redactor([]))
        return self.hydrator.hydrate(snapshot, journal)
