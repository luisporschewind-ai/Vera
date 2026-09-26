from pathlib import Path

import pytest
from typer.testing import CliRunner

from vera.cli import app


def test_config_show_never_prints_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-do-not-print")
    result = CliRunner().invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "sk-do-not-print" not in result.stdout
    assert "DEEPSEEK_API_KEY" not in result.stdout
    assert "limits" in result.stdout


def test_config_show_does_not_expose_invalid_user_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "config.toml"
    user.write_text(
        '[providers.bad]\nbase_url="https://example.com/v1"\n'
        'model="m"\napi_key_env="BAD_API_KEY"\napi_key="sk-private-in-config"\n'
    )
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(user))
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(tmp_path / "missing.json"))
    result = CliRunner().invoke(app, ["config", "show"])
    assert result.exit_code != 0
    assert "sk-private-in-config" not in result.stdout
    assert "sk-private-in-config" not in str(result.exception)
