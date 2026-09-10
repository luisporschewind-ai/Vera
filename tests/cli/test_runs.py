from typer.testing import CliRunner

from vera.cli import app


def test_runs_list_is_available() -> None:
    result = CliRunner().invoke(app, ["runs", "list"])
    assert result.exit_code == 0
