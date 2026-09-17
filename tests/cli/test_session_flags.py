from pathlib import Path

from typer.testing import CliRunner

from vera.cli import app
from vera.cli_options import normalize_resume_argv, parse_session_open_request
from vera.presentation.sanitize import sanitize_terminal_text
from vera.session.startup import SessionStartupError


def test_normalize_resume_argv_inserts_picker_sentinel() -> None:
    assert normalize_resume_argv(["-r"]) == ["-r", "__PICKER__"]
    assert normalize_resume_argv(["--resume"]) == ["--resume", "__PICKER__"]
    assert normalize_resume_argv(["-r", "--json"]) == ["-r", "__PICKER__", "--json"]
    assert normalize_resume_argv(["-r", "session_abc"]) == ["-r", "session_abc"]
    assert normalize_resume_argv(["--json", "-r"]) == ["--json", "-r", "__PICKER__"]


def test_default_and_continue_and_resume_forms() -> None:
    assert parse_session_open_request([]).mode == "new"
    assert parse_session_open_request(["-c"]).mode == "continue"
    assert parse_session_open_request(["--continue"]).mode == "continue"
    assert parse_session_open_request(["-r"]).mode == "resume_picker"
    assert parse_session_open_request(["--resume"]).mode == "resume_picker"
    identified = parse_session_open_request(["-r", "session_abc"])
    assert identified.mode == "resume_id"
    assert identified.session_id == "session_abc"
    long_form = parse_session_open_request(["--resume", "session_abc"])
    assert long_form.session_id == "session_abc"


def test_flags_compose_with_mode_and_workspace() -> None:
    request = parse_session_open_request(["--plain", "-c", "--workspace", "/tmp/demo"])
    assert request.mode == "continue"
    request = parse_session_open_request(["-r", "sid", "--json", "--workspace", "/tmp/demo"])
    assert request.mode == "resume_id"
    assert request.session_id == "sid"


def test_continue_and_resume_conflict() -> None:
    try:
        parse_session_open_request(["-c", "-r"])
    except SessionStartupError as exc:
        assert exc.code == "continue_resume_conflict"
    else:
        raise AssertionError("expected conflict")


def test_duplicate_resume_and_extra_positional() -> None:
    try:
        parse_session_open_request(["-r", "a", "-r", "b"])
    except SessionStartupError as exc:
        assert exc.code == "duplicate_resume"
    else:
        raise AssertionError("expected duplicate")
    try:
        parse_session_open_request(["-r", "sid", "extra"])
    except SessionStartupError as exc:
        assert exc.code == "extra_positional"
    else:
        raise AssertionError("expected extra")


def test_subcommands_do_not_consume_session_flags() -> None:
    assert parse_session_open_request(["run", "hello"]).mode == "new"
    assert parse_session_open_request(["eval", "list"]).mode == "new"
    assert parse_session_open_request(["runs", "list", "-c"]).mode == "new"


def test_help_shows_optional_resume_and_run_resume_wording() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    text = sanitize_terminal_text(result.stdout)
    assert "-r" in text
    assert "--resume" in text
    assert "--continue" in text or "-c" in text
    assert "SESSION" in text.upper() or "session" in text.lower()


def test_json_resume_without_id_requires_explicit_session(tmp_path: Path, monkeypatch) -> None:
    from vera.bootstrap import RuntimeDependencies
    from vera.config import Limits, VeraConfig
    from vera.models.base import FakeModelAdapter
    from vera.runtime.engine import VeraRuntime
    from vera.terminal.mode import PresentationMode, TerminalCapabilities
    from vera.tools.registry import ToolRegistry

    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state"),
        config=VeraConfig(state_dir=tmp_path / "state", limits=Limits(), providers={}),
        installation_id="cli-test",
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    monkeypatch.setattr(
        "vera.cli.detect_terminal_capabilities",
        lambda: TerminalCapabilities(
            stdin_tty=False, stdout_tty=False, term="dumb", columns=80, rows=24
        ),
    )
    monkeypatch.setattr(
        "vera.cli.select_mode",
        lambda **_kwargs: PresentationMode.JSON,
    )
    result = CliRunner().invoke(app, ["--json", "-r", "--workspace", str(workspace)])
    assert result.exit_code == 2
    combined = f"{result.stdout}{result.stderr}"
    assert "requires an argument" not in combined
    assert "\u001b" not in result.stdout
    assert "session.jsonl" not in result.stdout


def test_cli_bare_resume_does_not_require_click_argument(tmp_path: Path, monkeypatch) -> None:
    from vera.bootstrap import RuntimeDependencies
    from vera.config import Limits, VeraConfig
    from vera.models.base import FakeModelAdapter
    from vera.runtime.engine import VeraRuntime
    from vera.terminal.mode import TerminalCapabilities
    from vera.tools.registry import ToolRegistry

    workspace = tmp_path / "project"
    workspace.mkdir()
    deps = RuntimeDependencies(
        runtime=VeraRuntime(FakeModelAdapter([]), ToolRegistry(), tmp_path / "state"),
        config=VeraConfig(state_dir=tmp_path / "state", limits=Limits(), providers={}),
        installation_id="cli-test",
    )
    monkeypatch.setattr("vera.cli.build_runtime", lambda *_args, **_kwargs: deps)
    monkeypatch.setattr(
        "vera.cli.detect_terminal_capabilities",
        lambda: TerminalCapabilities(
            stdin_tty=False, stdout_tty=False, term="dumb", columns=80, rows=24
        ),
    )
    result = CliRunner().invoke(app, ["--plain", "-r", "--workspace", str(workspace)])
    combined = f"{result.stdout}{result.stderr}{result.output}"
    assert result.exit_code == 2
    assert "requires an argument" not in combined
    assert "非交互" in combined or "session-id" in combined
