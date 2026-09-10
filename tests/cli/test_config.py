from typer.testing import CliRunner

from vera.cli import app


def test_config_show_never_prints_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-do-not-print")
    result = CliRunner().invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "sk-do-not-print" not in result.stdout
    assert "DEEPSEEK_API_KEY" not in result.stdout
    assert "limits" in result.stdout
