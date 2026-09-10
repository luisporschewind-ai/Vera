from typer.testing import CliRunner

from vera.cli import app


def test_rollback_requires_target() -> None:
    result = CliRunner().invoke(app, ["rollback"])
    assert result.exit_code != 0
