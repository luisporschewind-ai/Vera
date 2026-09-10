from typer.testing import CliRunner

from vera.cli import app


def test_help_lists_formal_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "runs", "rollback", "config"):
        assert command in result.stdout
