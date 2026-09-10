from pathlib import Path

from vera.cli_driver import drive_run
from vera.contracts.commands import StartRun

from .fakes import make_changeset_runtime, make_two_approval_runtime


def test_drive_run_streams_batches_before_two_approval_decisions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    runtime = make_two_approval_runtime(workspace, tmp_path / "state")
    decisions = ["approve", "approve"]
    trace: list[tuple[str, str]] = []

    def on_events(batch) -> None:
        trace.append(("events", batch[-1].type))

    def decide(event):
        trace.append(("decide", str(event.payload["kind"])))
        return decisions.pop(0)

    events = drive_run(
        runtime,
        StartRun(goal="edit", workspace_root=workspace, model_profile="fake"),
        decide,
        on_events,
    )

    assert [event.type for event in events].count("approval.required") == 2
    assert events[-1].type == "run.completed"
    assert target.read_text(encoding="utf-8") == "new\n"
    assert trace == [
        ("events", "approval.required"),
        ("decide", "changeset"),
        ("events", "approval.required"),
        ("decide", "command"),
        ("events", "run.completed"),
    ]


def test_drive_run_cancel_keeps_target_unchanged(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    runtime = make_changeset_runtime(workspace, tmp_path / "state")

    events = drive_run(
        runtime,
        StartRun(goal="edit", workspace_root=workspace, model_profile="fake"),
        lambda _event: "cancel",
        lambda _batch: None,
    )

    assert events[-1].type == "run.cancelled"
    assert target.read_text(encoding="utf-8") == "old\n"
