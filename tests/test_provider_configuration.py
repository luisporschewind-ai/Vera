"""User-owned model profile state and catalog behavior."""

from pathlib import Path

import pytest

from vera.config import ConfigurationError, ProviderConfig
from vera.provider_configuration import ProviderConfigurationService


def test_catalog_selection_persists_without_a_secret(tmp_path: Path) -> None:
    path = tmp_path / "model_profiles.json"
    service = ProviderConfigurationService(path)
    profiles = service.list_profiles()
    assert {item.profile_id for item in profiles} == {
        "deepseek-flash",
        "glm-4.6",
        "openai-gpt-4.1-mini",
        "openai-gpt-4.1",
    }
    assert service.default_profile() is None
    service.enable("openai-gpt-4.1-mini")
    service.enable("deepseek-flash")
    service.move_before("deepseek-flash", "openai-gpt-4.1-mini")
    service.set_default("openai-gpt-4.1-mini")
    reloaded = ProviderConfigurationService(path)
    assert reloaded.default_profile() == "openai-gpt-4.1-mini"
    assert [item.profile_id for item in reloaded.list_profiles()[:2]] == [
        "deepseek-flash",
        "openai-gpt-4.1-mini",
    ]
    assert path.stat().st_mode & 0o777 == 0o600
    assert "fake-secret" not in path.read_text()


def test_disabling_default_requires_new_default(tmp_path: Path) -> None:
    service = ProviderConfigurationService(tmp_path / "models.json")
    service.enable("deepseek-flash")
    service.set_default("deepseek-flash")
    with pytest.raises(ConfigurationError, match="default"):
        service.disable("deepseek-flash")
    assert ProviderConfigurationService(service.path).default_profile() == "deepseek-flash"


def test_custom_profile_and_managed_override_legacy(tmp_path: Path) -> None:
    service = ProviderConfigurationService(tmp_path / "models.json")
    custom = ProviderConfig(
        base_url="https://custom.example/v1", model="custom-model", api_key_env="CUSTOM_API_KEY"
    )
    service.add_custom(custom, "my-model")
    service.enable("my-model")
    legacy = {
        "my-model": ProviderConfig(
            base_url="https://old.example/v1", model="old", api_key_env="OLD_API_KEY"
        )
    }
    assert (
        str(service.effective_providers(legacy)["my-model"].base_url) == "https://custom.example/v1"
    )
    assert legacy["my-model"].model == "old"


def test_custom_profile_id_must_be_cli_addressable(tmp_path: Path) -> None:
    service = ProviderConfigurationService(tmp_path / "models.json")
    custom = ProviderConfig(
        base_url="https://custom.example/v1", model="custom-model", api_key_env="CUSTOM_API_KEY"
    )
    with pytest.raises(ConfigurationError):
        service.add_custom(custom, "bad id")
    assert not service.path.exists()


@pytest.mark.parametrize(
    "body", ['{"version": 2}', "{broken", '{"version": 1, "enabled": ["ghost"]}']
)
def test_corrupt_or_future_managed_config_fails_closed(tmp_path: Path, body: str) -> None:
    path = tmp_path / "models.json"
    path.write_text(body)
    with pytest.raises(ConfigurationError):
        ProviderConfigurationService(path).list_profiles()
    assert path.read_text() == body


def test_invalid_managed_secret_is_not_chained_into_public_error(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(
        '{"version":1,"enabled":[],"order":[],"default":null,'
        '"custom_profiles":{"bad":{"base_url":"https://example.test/v1",'
        '"model":"m","api_key_env":"BAD_API_KEY","api_key":"sk-private"}},'
        '"overrides":{}}'
    )
    with pytest.raises(ConfigurationError) as caught:
        ProviderConfigurationService(path).list_profiles()
    assert "sk-private" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_catalog_removal_preserves_choice_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "models.json"
    service = ProviderConfigurationService(path)
    service.enable("deepseek-flash")
    service.set_default("deepseek-flash")
    import vera.provider_configuration as module

    monkeypatch.setattr(
        module,
        "CATALOG_BY_ID",
        {name: entry for name, entry in module.CATALOG_BY_ID.items() if name != "deepseek-flash"},
    )
    monkeypatch.setattr(
        module,
        "MODEL_CATALOG",
        tuple(entry for entry in module.MODEL_CATALOG if entry.profile_id != "deepseek-flash"),
    )
    reloaded = ProviderConfigurationService(path)
    retired = next(item for item in reloaded.list_profiles() if item.profile_id == "deepseek-flash")
    assert retired.enabled is True
    assert retired.default is True
    assert retired.valid is False
    assert retired.reason == "catalog_unavailable"
    assert reloaded.default_profile() == "deepseek-flash"


def test_managed_profiles_are_used_by_load_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vera.config import load_config

    managed = tmp_path / "models.json"
    user = tmp_path / "config.toml"
    user.write_text(
        '[providers.deepseek-flash]\nbase_url="https://old.example/v1"\n'
        'model="old"\napi_key_env="OLD_API_KEY"\n'
    )
    monkeypatch.setenv("VERA_MODEL_PROFILES_FILE", str(managed))
    monkeypatch.setenv("VERA_USER_CONFIG_FILE", str(user))
    service = ProviderConfigurationService(managed)
    service.enable("deepseek-flash")
    service.set_default("deepseek-flash")
    config = load_config(tmp_path / "workspace", {})
    assert config.providers["deepseek-flash"].model == "deepseek-flash"
    assert config.default_model_profile == "deepseek-flash"
    assert "old" in user.read_text()
