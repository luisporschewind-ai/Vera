from pathlib import Path

from typer.testing import CliRunner

from tests.cli.test_session import FakeGitRunner, ScriptedIO
from tests.recovery.helpers import PartialRecoveryFixture, make_snapshot
from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.cli_session import InteractiveSession
from vera.config import Limits, VeraConfig
from vera.contracts.commands import StartRun
from vera.contracts.recovery import RecoveryStage
from vera.models.base import FakeModelAdapter, ModelToolCall, ModelTurn
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.redaction import Redactor
from vera.runtime.engine import VeraRuntime
from vera.session.status import SessionStatusService
from vera.tools.registry import ToolRegistry


def _proposal() -> ModelTurn:
    return ModelTurn(
        finish_reason="tool_calls",
        tool_calls=(
            ModelToolCall(
                call_id="1",
                name="propose_changeset",
                arguments={
                    "summary": "edit",
                    "changes": [
                        {
                            "operation": "update",
                            "path": "hello.txt",
                            "after_content": "new\n",
                        }
                    ],
                },
            ),
        ),
    )


def _deps(runtime: VeraRuntime, state_dir: Path) -> RuntimeDependencies:
    return RuntimeDependencies(
        runtime=runtime,
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )


def test_recover_help_lists_resume_and_abandon() -> None:
    result = CliRunner().invoke(app, ["recover", "--help"])
    assert result.exit_code == 0
    assert "resume" in result.stdout
    assert "abandon" in result.stdout


def test_json_recover_resume_cancels_without_writing(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    first = VeraRuntime(
        FakeModelAdapter([_proposal()]),
        ToolRegistry(),
        state_dir,
        snapshot_store=RecoverySnapshotStore(state_dir),
        installation_id="install-1",
    )
    approval = next(
        event
        for event in first.handle(
            StartRun(goal="edit", workspace_root=workspace, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    second = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        state_dir,
        snapshot_store=RecoverySnapshotStore(state_dir),
        installation_id="install-1",
    )
    monkeypatch.setattr(
        "vera.cli.build_runtime", lambda *_args, **_kwargs: _deps(second, state_dir)
    )
    result = CliRunner().invoke(app, ["recover", "resume", approval.run_id, "--json"])

    assert result.exit_code == 2
    assert '"type":"run.cancelled"' in result.stdout
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert "sk-" not in result.stdout
    assert "Vera >" not in result.stdout


def test_json_recover_abandon_safe_and_unsafe(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(
        "vera.cli.build_runtime",
        lambda *_args, **_kwargs: _deps(runtime, fixture.state_dir),
    )
    abandoned = CliRunner().invoke(app, ["recover", "abandon", "run_safe", "--json"])
    refused = CliRunner().invoke(app, ["recover", "abandon", "run_1", "--json"])

    assert abandoned.exit_code == 0
    assert '"type":"recovery.abandoned"' in abandoned.stdout
    assert refused.exit_code == 5
    assert '"type":"recovery.manual_required"' in refused.stdout
    assert fixture.after_file.read_bytes() == b"after-b\n"


def test_session_resume_eof_cancels_safely(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("old\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    runtime = VeraRuntime(
        FakeModelAdapter([_proposal()]),
        ToolRegistry(),
        state_dir,
        snapshot_store=RecoverySnapshotStore(state_dir),
        installation_id="install-1",
    )
    approval = next(
        event
        for event in runtime.handle(
            StartRun(goal="edit", workspace_root=workspace, model_profile="fake")
        )
        if event.type == "approval.required"
    )
    io = ScriptedIO([f"/resume {approval.run_id}", EOFError()])
    session = InteractiveSession(
        _deps(runtime, state_dir),
        workspace,
        "fake",
        io,
        status_service=SessionStatusService(
            version_reader=lambda: "0.1.0",
            git_runner=FakeGitRunner(),
        ),
    )
    assert session.run() == 0
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "old\n"
    assert runtime.adapter.requests  # original start called the model
    output = "\n".join(io.output)
    assert "已取消" in output or "approval" in output.lower() or "开始恢复" in output


def test_session_help_lists_resume_and_abandon(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state")
    io = ScriptedIO(["/help", "/exit"])
    session = InteractiveSession(
        _deps(runtime, tmp_path / "state"),
        workspace,
        "fake",
        io,
        status_service=SessionStatusService(
            version_reader=lambda: "0.1.0",
            git_runner=FakeGitRunner(),
        ),
    )
    assert session.run() == 0
    output = "\n".join(io.output)
    assert "/resume" in output
    assert "/abandon" in output
