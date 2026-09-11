from pathlib import Path

from tests.recovery.helpers import PartialRecoveryFixture, make_snapshot
from vera.contracts.commands import AbandonRun
from vera.contracts.recovery import RecoveryStage
from vera.models.base import FakeModelAdapter
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.redaction import Redactor
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_abandon_only_accepts_safe_to_abandon(tmp_path: Path) -> None:
    fixture = PartialRecoveryFixture(tmp_path)
    journal = EventJournal(fixture.state_dir, "run_safe", Redactor([]))
    journal.append(
        "run.started",
        {
            "goal": "edit",
            "workspace_root": str(fixture.workspace),
            "model_profile": "fake",
            "kind": "task",
        },
    )
    RecoverySnapshotStore(fixture.state_dir).save(
        make_snapshot(
            fixture.workspace,
            files=(),
            stage=RecoveryStage.STARTED,
            pending=False,
        ).model_copy(update={"run_id": "run_safe", "last_event_sequence": 1})
    )
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        fixture.state_dir,
        snapshot_store=RecoverySnapshotStore(fixture.state_dir),
        installation_id="install-1",
    )

    safe_events = tuple(runtime.handle(AbandonRun(run_id="run_safe")))
    unsafe_events = tuple(runtime.handle(AbandonRun(run_id="run_1")))

    assert safe_events[-1].type == "recovery.abandoned"
    assert unsafe_events[-1].type == "recovery.manual_required"
    assert fixture.after_file.read_bytes() == b"after-b\n"
    assert runtime.coordinator.scan("run_safe") == ()
