from pathlib import Path

from typer.testing import CliRunner

from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.config import Limits, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def fake_dependencies(workspace: Path, state_dir: Path) -> RuntimeDependencies:
    return RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir),
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )


def test_plain_mode_has_no_dynamic_terminal_sequences(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_a, **_k: deps)
    result = CliRunner().invoke(
        app,
        ["--workspace", str(workspace), "--model", "fake", "--plain"],
        input="/status\n/exit\n",
    )
    assert result.exit_code == 0
    assert "\x1b[?1049h" not in result.stdout
    assert "\x1b[2K" not in result.stdout


def test_plain_and_json_conflict(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_a, **_k: deps)
    result = CliRunner().invoke(
        app,
        ["--workspace", str(workspace), "--model", "fake", "--plain", "--json"],
    )
    assert result.exit_code == 2


def test_legacy_run_json_remains_raw_event_envelopes(tmp_path: Path, monkeypatch) -> None:
    import json

    from vera.models.base import ModelTurn

    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = RuntimeDependencies(
        runtime=VeraRuntime(
            FakeModelAdapter([ModelTurn(assistant_text="hello", finish_reason="stop")]),
            ToolRegistry(),
            tmp_path / "state",
        ),
        config=VeraConfig(state_dir=tmp_path / "state", limits=Limits(), providers={}),
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_a, **_k: deps)
    result = CliRunner().invoke(
        app,
        ["run", "hello", "--workspace", str(workspace), "--json"],
    )
    assert result.exit_code == 0
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert records
    assert all("record_type" not in record for record in records)
    assert records[-1]["type"] == "run.completed"
