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


def test_bare_vera_starts_session_in_resolved_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)

    result = CliRunner().invoke(
        app,
        ["--workspace", str(workspace), "--model", "fake"],
        input="/exit\n",
    )

    assert result.exit_code == 0
    assert str(workspace.resolve()) in result.stdout
    assert "Vera >" in result.stdout
    assert "Model" in result.stdout or "Workspace" in result.stdout


def test_bare_vera_rejects_non_directory_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = CliRunner().invoke(app, ["--workspace", str(missing)])

    assert result.exit_code != 0
    assert "工作区必须是现有目录" in result.stdout
