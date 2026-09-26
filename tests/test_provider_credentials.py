"""Private provider values never become project configuration."""

from pathlib import Path

import pytest

from vera.config import ConfigurationError, UnsafeProviderEnvironment
from vera.provider_credentials import (
    key_status,
    read_provider_environment,
    set_provider_key,
)


def test_key_update_preserves_other_values_and_environment_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "provider.env"
    source.write_text("GLM_API_KEY=glm-fake\nVERA_GLM_MODEL=glm-4.6\n")
    source.chmod(0o600)
    set_provider_key("OPENAI_API_KEY", "openai-fake", source)
    values = read_provider_environment(
        frozenset({"GLM_API_KEY", "OPENAI_API_KEY", "VERA_GLM_MODEL"}), source
    )
    assert values == {
        "GLM_API_KEY": "glm-fake",
        "VERA_GLM_MODEL": "glm-4.6",
        "OPENAI_API_KEY": "openai-fake",
    }
    assert source.stat().st_mode & 0o777 == 0o600
    assert key_status("OPENAI_API_KEY", values) == "configured"
    monkeypatch.setenv("OPENAI_API_KEY", "process-fake")
    assert key_status("OPENAI_API_KEY", values) == "overridden_by_environment"


def test_untrusted_name_in_private_file_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "provider.env"
    source.write_text("UNTRUSTED_API_KEY=fake\n")
    source.chmod(0o600)
    with pytest.raises(UnsafeProviderEnvironment, match="line 1"):
        read_provider_environment(frozenset({"OPENAI_API_KEY"}), source)


@pytest.mark.parametrize(
    "body", ["OPENAI_API_KEY=$(whoami)\n", "OPENAI_API_KEY=a\nOPENAI_API_KEY=b\n"]
)
def test_private_file_rejects_shell_and_duplicate_names(tmp_path: Path, body: str) -> None:
    source = tmp_path / "provider.env"
    source.write_text(body)
    source.chmod(0o600)
    with pytest.raises(UnsafeProviderEnvironment):
        read_provider_environment(frozenset({"OPENAI_API_KEY"}), source)


def test_private_file_rejects_symlink_and_public_mode(tmp_path: Path) -> None:
    source = tmp_path / "provider.env"
    source.write_text("OPENAI_API_KEY=fake\n")
    source.chmod(0o600)
    link = tmp_path / "link.env"
    link.symlink_to(source)
    with pytest.raises(UnsafeProviderEnvironment):
        read_provider_environment(frozenset({"OPENAI_API_KEY"}), link)
    with pytest.raises(UnsafeProviderEnvironment):
        set_provider_key("OPENAI_API_KEY", "replacement", link)
    source.chmod(0o644)
    with pytest.raises(UnsafeProviderEnvironment, match="mode 0600"):
        read_provider_environment(frozenset({"OPENAI_API_KEY"}), source)


@pytest.mark.parametrize("name", ["lower_API_KEY", "OPENAI_KEY", "OPENAI_API_KEY;X", "X API_KEY"])
def test_invalid_reference_cannot_be_written(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigurationError):
        set_provider_key(name, "fake", tmp_path / "provider.env")


@pytest.mark.parametrize("value", ["", "a\nb", "a\r", "$(whoami)", 'fake"quote'])
def test_invalid_key_value_cannot_be_written(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError):
        set_provider_key("OPENAI_API_KEY", value, tmp_path / "provider.env")
    assert not (tmp_path / "provider.env").exists()
