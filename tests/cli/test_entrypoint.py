from pathlib import Path

from typer.testing import CliRunner

from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.config import Limits, VeraConfig
from vera.models.base import FakeModelAdapter
from vera.runtime.engine import VeraRuntime
from vera.terminal.mode import PresentationMode, TerminalCapabilities
from vera.tools.registry import ToolRegistry


def fake_dependencies(workspace: Path, state_dir: Path) -> RuntimeDependencies:
    return RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), state_dir),
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )


def supported_tty() -> TerminalCapabilities:
    return TerminalCapabilities(
        stdin_tty=True, stdout_tty=True, term="xterm-256color", columns=80, rows=24
    )


def test_vera_defaults_to_tui_in_tty(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    monkeypatch.setattr("vera.cli.detect_terminal_capabilities", supported_tty)
    calls: list[tuple[object, ...]] = []

    def fake_launch(controller, workspace_path, model_profile, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append((controller, workspace_path, model_profile))
        return 0

    monkeypatch.setattr("vera.terminal.app.launch_tui", fake_launch)

    result = CliRunner().invoke(app, ["--workspace", str(workspace), "--model", "fake"])

    assert result.exit_code == 0
    assert len(calls) == 1


def test_vera_plain_keeps_existing_session(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)

    result = CliRunner().invoke(
        app,
        ["--workspace", str(workspace), "--model", "fake", "--plain"],
        input="/exit\n",
    )

    assert result.exit_code == 0
    assert "Vera >" in result.stdout


def test_vera_rejects_default_without_tty(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    monkeypatch.setattr(
        "vera.cli.detect_terminal_capabilities",
        lambda: TerminalCapabilities(
            stdin_tty=False, stdout_tty=False, term="", columns=80, rows=24
        ),
    )

    result = CliRunner().invoke(app, ["--workspace", str(workspace), "--model", "fake"])

    assert result.exit_code == 2
    assert "--plain" in result.stderr or "--plain" in result.stdout


def test_vera_tui_import_failure_hints_plain(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    monkeypatch.setattr("vera.cli.detect_terminal_capabilities", supported_tty)

    def failing_launch(_deps, _workspace_path, _model):  # type: ignore[no-untyped-def]
        import typer

        typer.echo("无法启动 Textual TUI（textual missing）。请改用 --plain。", err=True)
        return 2

    monkeypatch.setattr("vera.cli._launch_tui_session", failing_launch)
    result = CliRunner().invoke(app, ["--workspace", str(workspace), "--model", "fake"])
    assert result.exit_code == 2
    assert "--plain" in (result.stderr + result.stdout)


def test_bare_vera_rejects_non_directory_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = CliRunner().invoke(app, ["--workspace", str(missing), "--plain"])

    assert result.exit_code != 0
    assert "工作区必须是现有目录" in result.stdout


def test_status_and_commands_hide_provider_secrets(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-render")
    monkeypatch.setenv("VERA_DEEPSEEK_BASE_URL", "https://must-not-render.example")

    result = CliRunner().invoke(
        app,
        ["--workspace", str(workspace), "--model", "fake", "--plain"],
        input="/status\n/context\n/permissions\n/model\n/exit\n",
    )

    assert result.exit_code == 0
    assert "must-not-render" not in result.stdout
    assert "https://must-not-render.example" not in result.stdout


def test_subcommand_run_does_not_start_tui(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = fake_dependencies(workspace, tmp_path / "state")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    calls: list[int] = []
    monkeypatch.setattr("vera.cli._launch_tui_session", lambda *_a, **_k: calls.append(1) or 0)
    monkeypatch.setattr("vera.cli.detect_terminal_capabilities", supported_tty)

    result = CliRunner().invoke(
        app,
        ["--workspace", str(workspace), "--model", "fake", "run", "hello", "--json"],
    )

    assert calls == []
    assert result.exit_code in {0, 4, 5}
    assert PresentationMode.TUI.value == "tui"
