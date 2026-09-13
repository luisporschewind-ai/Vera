from pathlib import Path

from vera.cli_driver import drive_run
from vera.cli_exit_codes import SUCCESS, USER_CANCEL, exit_code_for_events
from vera.contracts.commands import StartRun
from vera.contracts.compatibility import current_compatibility_manifest
from vera.session.command_catalog import CommandCatalog
from vera.session.controller import SessionSnapshot

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


def test_plain_driver_uses_frozen_core_commands_not_cli_text() -> None:
    names = {item.name for item in current_compatibility_manifest().commands}
    assert "start_run" in names
    assert "resolve_approval" in names
    assert "cancel_run" in names


def test_session_catalog_is_shared_across_driver_surface() -> None:
    catalog = CommandCatalog()
    names = {item.name for item in catalog.all()}
    assert {
        "/diff",
        "/review",
        "/doctor",
        "/config",
        "/usage",
        "/shortcuts",
        "/theme",
    } <= names
    snapshot = SessionSnapshot(
        session_id="s1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )
    assert catalog.parse(["/help"]).handler == catalog.list("/help", snapshot)[0].handler


def test_oneshot_exit_codes_follow_core_terminal_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    approved = drive_run(
        make_changeset_runtime(workspace, tmp_path / "approved"),
        StartRun(goal="edit", workspace_root=workspace, model_profile="fake"),
        lambda _event: "approve",
        lambda _batch: None,
    )
    cancelled = drive_run(
        make_changeset_runtime(workspace, tmp_path / "cancelled"),
        StartRun(goal="edit", workspace_root=workspace, model_profile="fake"),
        lambda _event: "cancel",
        lambda _batch: None,
    )
    assert exit_code_for_events(approved) == SUCCESS
    assert approved[-1].type == "run.completed"
    assert exit_code_for_events(cancelled) == USER_CANCEL
    assert cancelled[-1].type == "run.cancelled"
