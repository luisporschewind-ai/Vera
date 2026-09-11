"""Read-only restart scanning for interrupted runs."""

from __future__ import annotations

from pathlib import Path

from vera.contracts.recovery import (
    RecoveryClassification,
    RecoveryReport,
    RecoveryStage,
)
from vera.persistence.journal import EventJournal, JournalCorrupt
from vera.persistence.recovery_snapshot import RecoverySnapshotError, RecoverySnapshotStore
from vera.persistence.run_store import RunStore
from vera.recovery.classifier import RecoveryClassifier
from vera.recovery.probe import WorkspaceEvidenceProbe
from vera.workspace.checkpoint import CheckpointStore

_TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})
_LEGACY_ACTIONS = ("inspect", "rollback")
_MANUAL_ACTIONS = ("inspect",)


class RecoveryCoordinator:
    def __init__(
        self,
        state_dir: Path,
        installation_id: str,
        *,
        run_store: RunStore | None = None,
        snapshot_store: RecoverySnapshotStore | None = None,
        probe: WorkspaceEvidenceProbe | None = None,
        classifier: RecoveryClassifier | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.installation_id = installation_id
        self.run_store = run_store or RunStore(state_dir)
        self.snapshot_store = snapshot_store or RecoverySnapshotStore(state_dir)
        self.probe = probe or WorkspaceEvidenceProbe(installation_id)
        self.classifier = classifier or RecoveryClassifier()

    def scan(self, run_id: str | None = None) -> tuple[RecoveryReport, ...]:
        if run_id is not None:
            report = self._scan_one(run_id)
            return () if report is None else (report,)
        reports: list[RecoveryReport] = []
        for item in self.run_store.iter_run_ids():
            report = self._scan_one(item)
            if report is not None:
                reports.append(report)
        return tuple(reports)

    def _scan_one(self, run_id: str) -> RecoveryReport | None:
        try:
            return self._classify_run(run_id)
        except (JournalCorrupt, RecoverySnapshotError, OSError, ValueError):
            return self._manual(run_id, "invalid_snapshot")

    def _classify_run(self, run_id: str) -> RecoveryReport | None:
        event_path = self.state_dir / "runs" / run_id / "events.jsonl"
        if not event_path.is_file():
            if self.snapshot_store.exists(run_id):
                return self._manual(run_id, "missing_journal")
            return None
        events = EventJournal.load_events(event_path, run_id)
        if not events:
            return None
        started = next((event for event in events if event.type == "run.started"), events[0])
        if started.payload.get("kind") == "compaction":
            return None
        if any(event.type in _TERMINAL_EVENTS for event in events):
            return None
        workspace = Path(str(started.payload.get("workspace_root", ".")))
        if not self.snapshot_store.exists(run_id):
            return RecoveryReport(
                run_id=run_id,
                classification=RecoveryClassification.LEGACY_NOT_RESUMABLE,
                stage=RecoveryStage.STARTED,
                workspace_root=workspace,
                evidence=(),
                allowed_actions=_LEGACY_ACTIONS,
                reason_code="legacy_not_resumable",
            )
        snapshot = self.snapshot_store.load(run_id)
        evidence = self.probe.inspect(snapshot)
        checkpoint_available: bool | None = None
        if snapshot.checkpoint_id is not None:
            try:
                CheckpointStore.load_manifest(self.state_dir, run_id)
                checkpoint_available = True
            except (OSError, ValueError):
                checkpoint_available = False
        return self.classifier.classify(
            snapshot,
            evidence,
            identity_matches=self.probe.identity_matches(snapshot),
            workspace_available=self.probe.workspace_available(snapshot),
            checkpoint_available=checkpoint_available,
        )

    def _manual(self, run_id: str, reason_code: str) -> RecoveryReport:
        workspace = Path(".")
        event_path = self.state_dir / "runs" / run_id / "events.jsonl"
        try:
            events = EventJournal.load_events(event_path, run_id)
            started = next((event for event in events if event.type == "run.started"), None)
            if started is not None:
                workspace = Path(str(started.payload.get("workspace_root", ".")))
        except (JournalCorrupt, OSError, ValueError):
            pass
        return RecoveryReport(
            run_id=run_id,
            classification=RecoveryClassification.MANUAL_REQUIRED,
            stage=RecoveryStage.STARTED,
            workspace_root=workspace,
            evidence=(),
            allowed_actions=_MANUAL_ACTIONS,
            reason_code=reason_code,
        )
