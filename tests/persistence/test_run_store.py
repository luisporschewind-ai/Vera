from pathlib import Path

import pytest

from vera.persistence.journal import EventJournal
from vera.persistence.run_store import RunStore
from vera.redaction import Redactor


def test_read_events_does_not_modify_existing_journal(tmp_path: Path, monkeypatch) -> None:
    event_path = tmp_path / "runs" / "run_1" / "events.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(
        '{"schema_version":1,"event_id":"evt-1","run_id":"run_1",'
        '"sequence":1,"timestamp":"2026-01-01T00:00:00Z",'
        '"type":"run.started","payload":{}}\n',
        encoding="utf-8",
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("read-only access must not chmod the journal")

    monkeypatch.setattr("vera.persistence.journal.os.chmod", fail_if_called)

    events = RunStore(tmp_path).read_events("run_1")

    assert [event.type for event in events] == ["run.started"]


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [("run.cancelled", "cancelled"), ("run.failed", "failed")],
)
def test_list_runs_derives_terminal_state_from_terminal_event(
    tmp_path: Path, event_type: str, expected: str
) -> None:
    journal = EventJournal(tmp_path, "run_1", Redactor([]))
    journal.append(
        "run.started",
        {"goal": "edit", "workspace_root": str(tmp_path), "model_profile": "fake"},
    )
    journal.append(event_type, {"reason": "test"})

    summaries = RunStore(tmp_path).list_runs()

    assert summaries[0].terminal_state == expected


def test_list_runs_hides_compaction_by_default(tmp_path: Path) -> None:
    task = EventJournal(tmp_path, "run_task", Redactor([]))
    task.append(
        "run.started",
        {
            "goal": "edit",
            "workspace_root": str(tmp_path),
            "model_profile": "fake",
            "kind": "task",
        },
    )
    task.append("run.completed", {"state": "completed", "outcome": "responded"})

    compact = EventJournal(tmp_path, "run_compact", Redactor([]))
    compact.append(
        "run.started",
        {
            "goal": "summarize",
            "workspace_root": str(tmp_path),
            "model_profile": "fake",
            "kind": "compaction",
        },
    )
    compact.append("run.completed", {"state": "completed", "outcome": "compacted"})

    store = RunStore(tmp_path)
    default_ids = [summary.run_id for summary in store.list_runs()]
    internal_ids = [summary.run_id for summary in store.list_runs(include_internal=True)]

    assert default_ids == ["run_task"]
    assert set(internal_ids) == {"run_task", "run_compact"}


def test_iter_run_ids_returns_sorted_safe_names(tmp_path: Path) -> None:
    EventJournal(tmp_path, "run_b", Redactor([]))
    EventJournal(tmp_path, "run_a", Redactor([]))
    (tmp_path / "runs" / "not a run").mkdir()
    (tmp_path / "runs" / "file.txt").write_text("x", encoding="utf-8")

    assert RunStore(tmp_path).iter_run_ids() == ("run_a", "run_b")
