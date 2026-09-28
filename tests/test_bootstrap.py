import os
from pathlib import Path

import pytest

from vera.bootstrap import build_runtime
from vera.config import ConfigurationError
from vera.provider_configuration import ProviderConfigurationService


def test_runtime_and_session_store_share_installation_id(
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
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dependencies = build_runtime(workspace)
    assert dependencies.installation_id
    assert dependencies.installation_id == dependencies.runtime.installation_id
    tool_names = {definition.name for definition in dependencies.runtime.registry.definitions()}
    assert {
        "git_status",
        "git_diff",
        "git_log",
        "git_show",
        "git_branch_list",
    } <= tool_names


def test_runtime_uses_explicit_user_default_and_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "provider.env"
    source.write_text("OPENAI_API_KEY=fake-key\n")
    source.chmod(0o600)
    managed = tmp_path / "model_profiles.json"
    service = ProviderConfigurationService(managed)
    service.enable("openai-gpt-4.1-mini")
    service.set_default("openai-gpt-4.1-mini")
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(managed))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    dependencies = build_runtime(workspace)
    assert dependencies.config.default_model_profile == "openai-gpt-4.1-mini"
    assert dependencies.runtime.adapter.provider.model == "gpt-4.1-mini"
    assert "OPENAI_API_KEY" not in os.environ
    summary = next(
        item
        for item in service.list_profiles_with_keys()
        if item.profile_id == "openai-gpt-4.1-mini"
    )
    assert summary.key_status == "configured"


def test_managed_profiles_do_not_block_explicit_legacy_user_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "provider.env"
    source.write_text("OPENAI_API_KEY=managed-fake\nPERSONAL_API_KEY=legacy-fake\n")
    source.chmod(0o600)
    user = tmp_path / "config.toml"
    user.write_text(
        '[providers.personal]\nbase_url="https://example.test/v1"\n'
        'model="personal-model"\napi_key_env="PERSONAL_API_KEY"\n'
    )
    managed = tmp_path / "model_profiles.json"
    service = ProviderConfigurationService(managed)
    service.enable("openai-gpt-4.1-mini")
    service.set_default("openai-gpt-4.1-mini")
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(managed))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(user))
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PERSONAL_API_KEY", raising=False)
    selected = build_runtime(workspace, "personal")
    assert selected.runtime.adapter.provider.model == "personal-model"


def test_runtime_rejects_private_key_file_inside_workspace_before_state_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "provider.env"
    source.write_text("OPENAI_API_KEY=fake-key\n")
    source.chmod(0o600)
    managed = tmp_path / "model_profiles.json"
    service = ProviderConfigurationService(managed)
    service.enable("openai-gpt-4.1-mini")
    service.set_default("openai-gpt-4.1-mini")
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(managed))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("VERA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="provider_key_in_workspace"):
        build_runtime(workspace)
    assert not (tmp_path / "state").exists()


def test_runtime_requires_key_for_user_enabled_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    managed = tmp_path / "model_profiles.json"
    service = ProviderConfigurationService(managed)
    service.enable("openai-gpt-4.1-mini")
    service.set_default("openai-gpt-4.1-mini")
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(managed))
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="missing_provider_key"):
        build_runtime(workspace)


def test_runtime_rejects_dangling_private_file_symlink_without_path_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "private-link.env"
    source.symlink_to(tmp_path / "missing-secret-file.env")
    monkeypatch.setenv("VERA_PROVIDER_ENV_FILE", str(source))
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(tmp_path / "missing.toml"))
    with pytest.raises(ConfigurationError) as caught:
        build_runtime(workspace)
    assert str(source) not in str(caught.value)
