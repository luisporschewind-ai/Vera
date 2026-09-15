from pathlib import Path

from typer.testing import CliRunner

from tests.recovery.helpers import make_snapshot
from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.config import Limits, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.persistence.journal import EventJournal
from vera.persistence.recovery_snapshot import RecoverySnapshotStore
from vera.redaction import Redactor
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry
from vera.workspace.changeset import sha256_bytes


def workspace_digest(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            values[str(path.relative_to(root))] = sha256_bytes(path.read_bytes())
    return values


class RecoveryHarness:
    def __init__(self, tmp_path: Path) -> None:
        self.workspace = tmp_path / "workspace"
        self.workspace.mkdir()
        (self.workspace / "app.py").write_text("before\n", encoding="utf-8")
        self.state_dir = tmp_path / "state"
        self.adapter = FakeModelAdapter([])
        self.runtime = VeraRuntime(
            self.adapter,
            ToolRegistry(),
            self.state_dir,
            snapshot_store=RecoverySnapshotStore(self.state_dir),
            installation_id="install-1",
        )
        self.deps = RuntimeDependencies(
            runtime=self.runtime,
            config=VeraConfig(state_dir=self.state_dir, limits=Limits(), providers={}),
        )
        journal = EventJournal(self.state_dir, "run_1", Redactor([]))
        journal.append(
            "run.started",
            {
                "goal": "edit",
                "workspace_root": str(self.workspace),
                "model_profile": "fake",
                "kind": "task",
            },
        )
        RecoverySnapshotStore(self.state_dir).save(
            make_snapshot(self.workspace).model_copy(update={"run_id": "run_1"})
        )


def test_recover_list_never_calls_model_or_changes_workspace(tmp_path: Path, monkeypatch) -> None:
    harness = RecoveryHarness(tmp_path)
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: harness.deps)
    before = workspace_digest(harness.workspace)
    result = CliRunner().invoke(app, ["recover", "list", "--json"])

    assert result.exit_code == 0
    assert '"type":"recovery.detected"' in result.stdout
    assert '"classification":"resumable_approval"' in result.stdout
    assert workspace_digest(harness.workspace) == before
    assert harness.adapter.requests == []
    assert "Vera >" not in result.stdout
    assert "\x1b" not in result.stdout


def test_recover_show_and_unknown_run(tmp_path: Path, monkeypatch) -> None:
    harness = RecoveryHarness(tmp_path)
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: harness.deps)
    shown = CliRunner().invoke(app, ["recover", "show", "run_1"])
    missing = CliRunner().invoke(app, ["recover", "show", "run_missing"])

    assert shown.exit_code == 0
    assert "run_1" in shown.stdout
    assert "resumable_approval" in shown.stdout
    assert missing.exit_code == 0
    assert "未找到" in missing.stdout


def test_recover_list_empty(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state"
    runtime = VeraRuntime(
        FakeModelAdapter([]),
        ToolRegistry(),
        state_dir,
        installation_id="install-1",
    )
    deps = RuntimeDependencies(
        runtime=runtime,
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    result = CliRunner().invoke(app, ["recover", "list"])
    assert result.exit_code == 0
    assert "暂无待恢复任务" in result.stdout


def test_help_lists_recover() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "recover" in result.stdout


def test_session_recover_is_readonly(tmp_path: Path) -> None:
    harness = RecoveryHarness(tmp_path)
    from tests.cli.test_session import FakeGitRunner
    from vera.cli_session import InteractiveSession
    from vera.session.status import SessionStatusService

    io_inputs: list[str | BaseException] = [
        "/recover",
        "/recover run_1",
        "/recover missing",
        "/abandon",
        "/exit",
    ]

    class ScriptedIO:
        def __init__(self) -> None:
            self.inputs = io_inputs
            self.output: list[str] = []

        def read(self, prompt: str) -> str:
            self.output.append(prompt)
            value = self.inputs.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value

        def write(self, text: str) -> None:
            self.output.append(text)

        def clear(self) -> None:
            return None

    io = ScriptedIO()
    session = InteractiveSession(
        harness.deps,
        harness.workspace,
        "fake",
        io,
        status_service=SessionStatusService(
            version_reader=lambda: "0.1.0",
            git_runner=FakeGitRunner(),
        ),
    )
    before = workspace_digest(harness.workspace)
    assert session.run() == 0
    output = "\n".join(io.output)
    assert "发现 1 个待恢复任务" in output
    assert "/recover" in output
    assert "resumable_approval" in output
    assert "未找到待恢复 run：missing" in output
    assert "用法：/abandon <run-id>" in output
    assert "可 abandon：" in output
    assert "run_1" in output
    assert workspace_digest(harness.workspace) == before
    assert harness.adapter.requests == []
