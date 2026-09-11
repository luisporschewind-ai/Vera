"""Read-only summaries and event access for completed or active runs."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from vera.config import RunSummary
from vera.contracts.events import EventEnvelope
from vera.persistence.errors import JournalCorrupt, StateVersionError
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import is_safe_run_id
from vera.persistence.run_manifest import RunManifestStore


class RunFormatStatus(StrEnum):
    CURRENT = "current"
    LEGACY = "legacy"
    CORRUPT = "corrupt"
    UNSUPPORTED = "unsupported"
    MISSING = "missing"


class RunStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self._manifests = RunManifestStore(state_dir)

    def format_status(self, run_id: str) -> RunFormatStatus:
        if not is_safe_run_id(run_id):
            return RunFormatStatus.MISSING
        run_dir = self.state_dir / "runs" / run_id
        event_path = run_dir / "events.jsonl"
        if not run_dir.is_dir() and not event_path.exists():
            return RunFormatStatus.MISSING
        try:
            if self._manifests.exists(run_id):
                self._manifests.load(run_id)
                if event_path.is_file():
                    EventJournal.load_events(event_path, run_id)
                return RunFormatStatus.CURRENT
            if event_path.is_file():
                EventJournal.load_events(event_path, run_id)
                return RunFormatStatus.LEGACY
            return RunFormatStatus.MISSING
        except StateVersionError as exc:
            if exc.code == "unsupported_version":
                return RunFormatStatus.UNSUPPORTED
            return RunFormatStatus.CORRUPT
        except (JournalCorrupt, OSError, ValueError):
            return RunFormatStatus.CORRUPT

    def read_events(self, run_id: str) -> tuple[EventEnvelope, ...]:
        path = self.state_dir / "runs" / run_id / "events.jsonl"
        if not path.is_file():
            return ()
        status = self.format_status(run_id)
        if status in {RunFormatStatus.CORRUPT, RunFormatStatus.UNSUPPORTED}:
            return ()
        return tuple(EventJournal.load_events(path, run_id))

    def list_runs(self, *, include_internal: bool = False) -> tuple[RunSummary, ...]:
        runs_dir = self.state_dir / "runs"
        if not runs_dir.exists():
            return ()
        summaries: list[RunSummary] = []
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir() or not is_safe_run_id(run_dir.name):
                continue
            status = self.format_status(run_dir.name)
            if status in {RunFormatStatus.CORRUPT, RunFormatStatus.UNSUPPORTED}:
                continue
            events = self.read_events(run_dir.name)
            if not events:
                continue
            started = next((event for event in events if event.type == "run.started"), events[0])
            if not include_internal and started.payload.get("kind") == "compaction":
                continue
            goal = str(started.payload.get("goal", ""))
            workspace = Path(str(started.payload.get("workspace_root", ".")))
            terminal_event = next(
                (
                    event
                    for event in reversed(events)
                    if event.type in {"run.completed", "run.failed", "run.cancelled"}
                ),
                None,
            )
            terminal = None
            if terminal_event is not None:
                terminal = terminal_event.payload.get("state") or terminal_event.type.removeprefix(
                    "run."
                )
            summaries.append(
                RunSummary(
                    run_id=run_dir.name,
                    workspace_root=workspace,
                    goal_summary=goal,
                    last_event_at=events[-1].timestamp,
                    terminal_state=str(terminal) if terminal is not None else None,
                )
            )
        summaries.sort(key=lambda item: item.last_event_at, reverse=True)
        return tuple(summaries)

    def iter_run_ids(self) -> tuple[str, ...]:
        runs_dir = self.state_dir / "runs"
        if not runs_dir.is_dir():
            return ()
        names = [
            item.name for item in runs_dir.iterdir() if item.is_dir() and is_safe_run_id(item.name)
        ]
        return tuple(sorted(names))
