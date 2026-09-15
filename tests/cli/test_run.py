from pathlib import Path

from typer.testing import CliRunner

from tests.cli.fakes import make_changeset_runtime
from vera.bootstrap import RuntimeDependencies
from vera.cli import app
from vera.config import Limits, ProviderConfig, VeraConfig
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.presentation.sanitize import sanitize_terminal_text
from vera.runtime.engine import VeraRuntime
from vera.tools.registry import ToolRegistry


def test_help_lists_formal_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    help_text = sanitize_terminal_text(result.stdout)
    for command in ("run", "runs", "rollback", "config"):
        assert command in help_text
    assert "--version" in help_text


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


def dependencies_with_text_turn(tmp_path: Path, text: str) -> RuntimeDependencies:
    state_dir = tmp_path / "state"
    return RuntimeDependencies(
        runtime=VeraRuntime(
            FakeModelAdapter([ModelTurn(assistant_text=text, finish_reason="stop")]),
            ToolRegistry(),
            state_dir,
        ),
        config=VeraConfig(state_dir=state_dir, limits=Limits(), providers={}),
    )


def test_json_plain_response_contains_events_without_human_output(
    tmp_path: Path, monkeypatch
) -> None:
    deps = dependencies_with_text_turn(tmp_path, "hello")
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)

    result = CliRunner().invoke(
        app,
        ["run", "Hello", "--workspace", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    assert '"type":"assistant.message"' in result.stdout
    assert '"outcome":"responded"' in result.stdout
    assert "Vera：" not in result.stdout
    assert "Vera >" not in result.stdout
    assert "\x1b" not in result.stdout


def test_json_run_uses_configured_provider_profile_name(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    deps = RuntimeDependencies(
        runtime=VeraRuntime(
            FakeModelAdapter([ModelTurn(assistant_text="hello", finish_reason="stop")]),
            ToolRegistry(),
            state_dir,
        ),
        config=VeraConfig(
            state_dir=state_dir,
            limits=Limits(),
            providers={
                "deepseek": ProviderConfig(
                    base_url="https://example.invalid",
                    model="deepseek-flash",
                    api_key_env="DEEPSEEK_API_KEY",
                )
            },
        ),
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)

    result = CliRunner().invoke(
        app,
        ["run", "Hello", "--workspace", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    assert '"model_profile":"deepseek"' in result.stdout
    assert '"model_profile":"default"' not in result.stdout
