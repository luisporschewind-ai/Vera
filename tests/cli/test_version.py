import json
from pathlib import Path

from typer.testing import CliRunner

from vera.cli import app
from vera.presentation.sanitize import sanitize_terminal_text
from vera.version import VersionIdentity


def _identity() -> VersionIdentity:
    return VersionIdentity(
        name="vera",
        version="0.1.0",
        location="/Users/admin/Vera/src/vera",
        install="editable",
        git_commit="abc1234",
        git_dirty=True,
    )


def test_version_flag_prints_identity_and_skips_session(monkeypatch) -> None:
    monkeypatch.setattr("vera.cli.current_identity", _identity)
    launched: list[int] = []
    monkeypatch.setattr("vera.cli._launch_tui_session", lambda *_a, **_k: launched.append(1) or 0)
    monkeypatch.setattr(
        "vera.cli.build_runtime",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("runtime")),
    )

    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "vera 0.1.0+abc1234.dirty" in result.stdout
    assert "/Users/admin/Vera/src/vera" in result.stdout
    assert "install: editable" in result.stdout
    assert launched == []


def test_version_short_flag_and_missing_workspace(monkeypatch) -> None:
    monkeypatch.setattr("vera.cli.current_identity", _identity)
    missing = Path("/no-such-vera-workspace")

    result = CliRunner().invoke(app, ["-V", "--workspace", str(missing)])

    assert result.exit_code == 0
    assert "vera 0.1.0+abc1234.dirty" in result.stdout
    assert "工作区必须是现有目录" not in result.stdout


def test_json_version_is_single_object_not_session(monkeypatch) -> None:
    monkeypatch.setattr("vera.cli.current_identity", _identity)

    result = CliRunner().invoke(app, ["--json", "--version"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["name"] == "vera"
    assert payload["version"] == "0.1.0"
    assert payload["display_version"] == "0.1.0+abc1234.dirty"
    assert payload["location"] == "/Users/admin/Vera/src/vera"
    assert payload["install"] == "editable"
    assert payload["git"] == {"commit": "abc1234", "dirty": True}
    assert "\u001b" not in result.stdout
    assert len(result.stdout.strip().splitlines()) == 1


def test_help_lists_version_option() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    help_text = sanitize_terminal_text(result.stdout)
    assert "--version" in help_text
    assert "-V" in help_text


def test_live_version_flag_reports_running_package() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "vera 0.1.0" in result.stdout
    assert "location:" in result.stdout
    assert "install:" in result.stdout
