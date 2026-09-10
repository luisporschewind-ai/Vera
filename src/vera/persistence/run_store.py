"""Read-only summaries and event access for completed or active runs."""

from __future__ import annotations

from pathlib import Path

from vera.config import RunSummary
from vera.contracts.events import EventEnvelope
from vera.persistence.journal import EventJournal


class RunStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def read_events(self, run_id: str) -> tuple[EventEnvelope, ...]:
        path = self.state_dir / "runs" / run_id / "events.jsonl"
        if not path.is_file():
            return ()
        return tuple(EventJournal.load_events(path, run_id))

    def list_runs(self) -> tuple[RunSummary, ...]:
        runs_dir = self.state_dir / "runs"
        if not runs_dir.exists():
            return ()
        summaries: list[RunSummary] = []
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            events = self.read_events(run_dir.name)
            if not events:
                continue
            started = next((event for event in events if event.type == "run.started"), events[0])
            goal = str(started.payload.get("goal", ""))
            workspace = Path(str(started.payload.get("workspace_root", ".")))
            terminal = next(
                (
                    event.payload.get("state")
                    for event in reversed(events)
                    if event.type in {"run.completed", "run.failed", "run.cancelled"}
                ),
                None,
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
