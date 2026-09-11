from pathlib import Path

from typer.testing import CliRunner

from tests.cli.fakes import make_changeset_runtime
from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.config import Limits, VeraConfig


def test_help_lists_formal_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "runs", "rollback", "config"):
        assert command in result.stdout


def test_json_run_stays_noninteractive_and_cancels_at_approval(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "hello.txt"
    target.write_text("old\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    deps = RuntimeDependencies(
        runtime=make_changeset_runtime(workspace, state_dir),
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)

    result = CliRunner().invoke(
        app,
        ["run", "edit", "--workspace", str(workspace), "--json"],
    )

    assert result.exit_code == 2
    assert "Vera >" not in result.stdout
    assert "approval >" not in result.stdout
    assert '"type":"run.cancelled"' in result.stdout
    assert target.read_text(encoding="utf-8") == "old\n"
