"""CLI model catalog and private key setup."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vera.cli import app


@pytest.fixture
def isolated_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(tmp_path / "models.json"))
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(tmp_path / "provider.env"))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return tmp_path


def test_models_list_and_selection_commands_persist(isolated_models: Path) -> None:
    runner = CliRunner()
    listed = runner.invoke(app, ["models", "list"])
    assert listed.exit_code == 0
    assert "openai-gpt-4.1-mini" in listed.stdout
    assert "missing" in listed.stdout
    assert runner.invoke(app, ["models", "enable", "openai-gpt-4.1-mini"]).exit_code == 0
    assert runner.invoke(app, ["models", "enable", "deepseek-flash"]).exit_code == 0
    assert (
        runner.invoke(
            app, ["models", "move", "deepseek-flash", "--before", "openai-gpt-4.1-mini"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["models", "default", "openai-gpt-4.1-mini"]).exit_code == 0
    current = runner.invoke(app, ["models", "list"])
    assert current.exit_code == 0
    assert "default" in current.stdout
    assert current.stdout.index("deepseek-flash") < current.stdout.index("openai-gpt-4.1-mini")
    assert "OPENAI_API_KEY" not in current.stdout


def test_key_set_requires_tty_and_never_echoes_value(isolated_models: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["models", "key", "set", "openai-gpt-4.1-mini"], input="fake-secret\n"
    )
    assert result.exit_code != 0
    assert "fake-secret" not in result.stdout
    assert not (isolated_models / "provider.env").exists()


def test_models_setup_requires_tty_before_secret_prompt(isolated_models: Path) -> None:
    result = CliRunner().invoke(app, ["models", "setup"], input="openai-gpt-4.1-mini\n")
    assert result.exit_code != 0
    assert not (isolated_models / "provider.env").exists()


def test_setup_saves_enabled_default_and_hidden_key(
    isolated_models: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vera.cli_models._require_tty", lambda: None)
    result = CliRunner().invoke(
        app,
        ["models", "setup"],
        input="openai-gpt-4.1-mini\ny\ny\ny\nfake-secret\nfake-secret\n",
    )
    assert result.exit_code == 0, result.output
    assert "fake-secret" not in result.output
    assert "fake-secret" in (isolated_models / "provider.env").read_text()
    assert "fake-secret" not in (isolated_models / "models.json").read_text()
    assert "openai-gpt-4.1-mini" in CliRunner().invoke(app, ["models", "list"]).stdout


def test_setup_requires_explicit_glm_region(
    isolated_models: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vera.cli_models._require_tty", lambda: None)
    invalid = CliRunner().invoke(app, ["models", "setup"], input="glm-4.6\nwrong\n")
    assert invalid.exit_code != 0
    assert (
        "glm-4.6" not in (isolated_models / "models.json").read_text()
        if (isolated_models / "models.json").exists()
        else True
    )


def test_models_list_keeps_legacy_user_profile_visible(isolated_models: Path) -> None:
    (isolated_models / "missing.toml").write_text(
        '[providers.personal]\nbase_url="https://example.test/v1"\n'
        'model="personal-model"\napi_key_env="PERSONAL_API_KEY"\n'
    )
    result = CliRunner().invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "personal" in result.stdout
    assert "PERSONAL_API_KEY" not in result.stdout
