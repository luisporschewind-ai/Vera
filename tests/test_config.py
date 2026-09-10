from pathlib import Path

import pytest

from vera.config import UnsafeProjectConfig, load_config


def write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_project_config_can_lower_but_not_raise_limits(tmp_path: Path) -> None:
    write_toml(tmp_path / ".vera" / "config.toml", "[limits]\nmax_model_turns = 10\n")
    assert load_config(tmp_path, {}).limits.max_model_turns == 10

    write_toml(tmp_path / ".vera" / "config.toml", "[limits]\nmax_model_turns = 21\n")
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
