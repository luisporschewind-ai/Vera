import os
from pathlib import Path

import pytest

from vera.bootstrap import build_runtime
from vera.config import (
    UnsafeProjectConfig,
    UnsafeProviderEnvironment,
    load_config,
    load_provider_environment,
)


def write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_conversation_limit_defaults_to_two_hundred_thousand(tmp_path: Path) -> None:
    config = load_config(tmp_path, {})
    assert config.limits.max_conversation_bytes == 200_000


def test_project_config_can_lower_but_not_raise_limits(tmp_path: Path) -> None:
    write_toml(tmp_path / ".vera" / "config.toml", "[limits]\nmax_model_turns = 10\n")
    assert load_config(tmp_path, {}).limits.max_model_turns == 10

    write_toml(tmp_path / ".vera" / "config.toml", "[limits]\nmax_model_turns = 21\n")
    with pytest.raises(UnsafeProjectConfig):
        load_config(tmp_path, {})

    write_toml(
        tmp_path / ".vera" / "config.toml",
        "[limits]\nmax_conversation_bytes = 100000\n",
    )
    assert load_config(tmp_path, {}).limits.max_conversation_bytes == 100_000

    write_toml(
        tmp_path / ".vera" / "config.toml",
        "[limits]\nmax_conversation_bytes = 200001\n",
    )
    with pytest.raises(UnsafeProjectConfig):
        load_config(tmp_path, {})


def test_config_priority_is_cli_then_environment_then_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_toml(tmp_path / ".vera" / "config.toml", "[limits]\nmax_model_turns = 10\n")
    monkeypatch.setenv("VERA_MAX_MODEL_TURNS", "12")
    assert load_config(tmp_path, {"limits": {"max_model_turns": 8}}).limits.max_model_turns == 8


def test_project_config_rejects_secrets_and_command_policy(tmp_path: Path) -> None:
    write_toml(tmp_path / ".vera" / "config.toml", 'api_key = "secret"\n')
    with pytest.raises(UnsafeProjectConfig):
        load_config(tmp_path, {})

    write_toml(
        tmp_path / ".vera" / "config.toml",
        'user_allowed_command_prefixes = [["rm"]]\n',
    )
    with pytest.raises(UnsafeProjectConfig):
        load_config(tmp_path, {})

    write_toml(
        tmp_path / ".vera" / "config.toml",
        'editor_argv = ["vim"]\n',
    )
    with pytest.raises(UnsafeProjectConfig):
        load_config(tmp_path, {})


def test_deepseek_environment_config_registers_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-secret")
    monkeypatch.setenv("VERA_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("VERA_DEEPSEEK_MODEL", "deepseek-flash")
    config = load_config(tmp_path, {})
    assert str(config.providers["deepseek"].base_url) == "https://api.deepseek.com/"
    assert config.providers["deepseek"].model == "deepseek-flash"
    assert config.providers["deepseek"].api_key_env == "DEEPSEEK_API_KEY"


def test_provider_environment_loads_known_values_without_overwriting_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text(
        "export DEEPSEEK_API_KEY=file-secret\n"
        "VERA_DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "VERA_DEEPSEEK_MODEL=deepseek-flash\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")

    load_provider_environment(source)

    assert os.environ["DEEPSEEK_API_KEY"] == "process-secret"
    assert os.environ["VERA_DEEPSEEK_BASE_URL"] == "https://api.deepseek.com"
    assert os.environ["VERA_DEEPSEEK_MODEL"] == "deepseek-flash"


def test_provider_environment_rejects_public_permissions(tmp_path: Path) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text("DEEPSEEK_API_KEY=secret\n", encoding="utf-8")
    source.chmod(0o644)

    with pytest.raises(UnsafeProviderEnvironment, match="mode 0600"):
        load_provider_environment(source)


def test_provider_environment_rejects_shell_syntax(tmp_path: Path) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text("DEEPSEEK_API_KEY=$(whoami)\n", encoding="utf-8")
    source.chmod(0o600)

    with pytest.raises(UnsafeProviderEnvironment, match="shell syntax"):
        load_provider_environment(source)


def test_build_runtime_loads_provider_environment_before_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "deepseek.env"
    source.write_text(
        "DEEPSEEK_API_KEY=test-secret\n"
        "VERA_DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "VERA_DEEPSEEK_MODEL=deepseek-flash\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("VERA_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("VERA_DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))

    dependencies = build_runtime(tmp_path)

    assert dependencies.config.providers["deepseek"].model == "deepseek-flash"
