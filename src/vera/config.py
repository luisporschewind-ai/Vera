"""Layered, safety-bounded configuration for Vera."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal

from platformdirs import user_config_path, user_state_path
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError, field_validator

from vera.models.capabilities import ModelCapabilities
from vera.redaction import DEFAULT_SECRET_POLICY


class UnsafeProjectConfig(ValueError):
    """Raised when project configuration attempts to bypass a safety boundary."""


class UnsafeProviderEnvironment(ValueError):
    """Raised when a private provider environment file is unsafe or malformed."""


class ConfigurationError(Exception):
    """Stable configuration failure with an operator-facing code and exit status."""

    def __init__(self, code: str, message: str, *, exit_code: int = 5) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_model_turns: int = Field(default=20, ge=1)
    max_tool_calls: int = Field(default=50, ge=1)
    max_file_bytes: int = Field(default=1_000_000, ge=1)
    max_tool_output_bytes: int = Field(default=100_000, ge=1)
    max_context_bytes: int = Field(default=2_000_000, ge=1)
    max_conversation_bytes: int = Field(default=200_000, ge=1)
    command_timeout_seconds: int = Field(default=120, ge=1)
    max_model_attempts: int = Field(default=2, ge=1)


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: AnyHttpUrl
    model: str
    api_key_env: str
    capabilities: ModelCapabilities = Field(default_factory=lambda: ModelCapabilities())
    output_token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    stream_usage_mode: Literal["provider_default", "include_usage"] = "provider_default"

    @field_validator("base_url")
    @classmethod
    def validate_endpoint(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("provider endpoint cannot include credentials, query or fragment")
        if value.scheme == "http":
            host = value.host or ""
            if host != "localhost":
                try:
                    if not ip_address(host).is_loopback:
                        raise ValueError("remote provider endpoint must use HTTPS")
                except ValueError as exc:
                    raise ValueError("remote provider endpoint must use HTTPS") from exc
        return value

    @field_validator("api_key_env")
    @classmethod
    def validate_key_reference(cls, value: str) -> str:
        if re.fullmatch(r"[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET)", value) is None:
            raise ValueError("provider key reference must be a secret environment name")
        return value

    @field_validator("model")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if re.fullmatch(r"\S{1,200}", value) is None:
            raise ValueError("provider model identifier is invalid")
        return value


class UiConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    animations: bool = True


class VeraConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state_dir: Path
    limits: Limits
    providers: dict[str, ProviderConfig]
    default_model_profile: str | None = None
    enabled_model_profiles: tuple[str, ...] = ()
    user_allowed_command_prefixes: tuple[tuple[str, ...], ...] = ()
    ui: UiConfig = Field(default_factory=UiConfig)
    editor_argv: tuple[str, ...] = ()


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    workspace_root: Path
    goal_summary: str
    last_event_at: datetime
    terminal_state: str | None


def user_skills_path() -> Path:
    """Return the user-local Skill root without creating it."""

    return user_config_path("Vera") / "skills"


_PROJECT_FORBIDDEN_KEYS = {
    *DEFAULT_SECRET_POLICY.sensitive_fields,
    "user_allowed_command_prefixes",
    "allowed_command_prefixes",
    "safe_commands",
    "editor_argv",
    "providers",
    "model",
    "model_profile",
    "api_key_env",
    "base_url",
    "model_catalog",
    "model_profiles",
    "default_profile",
    "enabled_profiles",
    "profile_order",
}

_PROVIDER_ENV_KEYS = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "VERA_DEEPSEEK_BASE_URL",
        "VERA_DEEPSEEK_MODEL",
        "GLM_API_KEY",
        "VERA_GLM_BASE_URL",
        "VERA_GLM_MODEL",
    }
)


def load_provider_environment(path: Path | None = None) -> None:
    """Load known provider values from a private key-value file without a shell."""
    from vera.provider_credentials import read_provider_environment

    for name, value in read_provider_environment(_PROVIDER_ENV_KEYS, path).items():
        os.environ.setdefault(name, value)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    return value


def load_user_providers() -> dict[str, ProviderConfig]:
    """Read legacy user-owned profiles without consulting a project workspace."""
    user_file = Path(
        os.environ.get("VERA_USER_CONFIG_FILE", str(user_config_path("Vera") / "config.toml"))
    )
    try:
        raw = _read_toml(user_file).get("providers", {})
        if not isinstance(raw, dict):
            raise ValueError("invalid providers")
        return {name: ProviderConfig.model_validate(value) for name, value in raw.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        raise ConfigurationError(
            "invalid_user_provider", "user provider configuration is invalid"
        ) from None


def _merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _find_forbidden_key(value: object) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in _PROJECT_FORBIDDEN_KEYS:
                return str(key)
            found = _find_forbidden_key(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_forbidden_key(nested)
            if found is not None:
                return found
    return None


def _env_limits() -> dict[str, object]:
    values: dict[str, Any] = {}
    if "VERA_MAX_MODEL_TURNS" in os.environ:
        values["max_model_turns"] = int(os.environ["VERA_MAX_MODEL_TURNS"])
    if "VERA_MAX_TOOL_CALLS" in os.environ:
        values["max_tool_calls"] = int(os.environ["VERA_MAX_TOOL_CALLS"])
    return values


def _env_providers(provider_values: Mapping[str, str] | None = None) -> dict[str, object]:
    values = dict(provider_values or {})
    values.update(os.environ)
    providers: dict[str, object] = {}
    if all(
        values.get(name)
        for name in ("DEEPSEEK_API_KEY", "VERA_DEEPSEEK_BASE_URL", "VERA_DEEPSEEK_MODEL")
    ):
        providers["deepseek"] = {
            "base_url": values["VERA_DEEPSEEK_BASE_URL"],
            "model": values["VERA_DEEPSEEK_MODEL"],
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    return providers


def load_config(
    workspace: Path,
    cli_overrides: Mapping[str, object],
    provider_values: Mapping[str, str] | None = None,
) -> VeraConfig:
    """Load defaults, user config, project config, environment, then CLI overrides."""

    defaults: dict[str, Any] = {"limits": Limits().model_dump(), "providers": {}}
    user_file = Path(
        os.environ.get(
            "VERA_USER_CONFIG_FILE",
            str(user_config_path("Vera") / "config.toml"),
        )
    )
    user_config = _read_toml(user_file)
    project_config = _read_toml(workspace / ".vera" / "config.toml")
    forbidden = _find_forbidden_key(project_config)
    if forbidden is not None:
        raise UnsafeProjectConfig(f"project config contains forbidden key: {forbidden}")

    user_limits = _merge({}, user_config.get("limits", {}))
    baseline_limits = _merge(defaults["limits"], user_limits)
    project_limits = project_config.get("limits", {})
    if isinstance(project_limits, dict):
        for key, value in project_limits.items():
            if key not in baseline_limits or not isinstance(value, (int, float)):
                continue
            if value > baseline_limits[key]:
                raise UnsafeProjectConfig(f"project limit cannot increase: {key}")

    merged = _merge(defaults, user_config)
    merged = _merge(merged, project_config)
    merged["providers"] = _merge(merged.get("providers", {}), _env_providers(provider_values))
    from vera.provider_configuration import ProviderConfigurationService

    profiles = ProviderConfigurationService()
    try:
        legacy_providers = {
            name: ProviderConfig.model_validate(value)
            for name, value in merged["providers"].items()
        }
    except (ValidationError, TypeError, AttributeError):
        raise ConfigurationError(
            "invalid_user_provider", "user provider configuration is invalid"
        ) from None
    merged["providers"] = profiles.effective_providers(legacy_providers)
    merged["default_model_profile"] = profiles.default_profile()
    merged["enabled_model_profiles"] = profiles.enabled_profiles()
    merged["limits"] = _merge(merged.get("limits", {}), _env_limits())
    merged = _merge(merged, cli_overrides)
    state_dir = os.environ.get("VERA_STATE_DIR")
    if state_dir is not None:
        merged["state_dir"] = state_dir
    else:
        merged.setdefault("state_dir", str(user_state_path("Vera")))
    merged.setdefault("user_allowed_command_prefixes", ())
    merged.setdefault("editor_argv", ())
    try:
        return VeraConfig.model_validate(merged)
    except ValidationError:
        raise ConfigurationError("invalid_config", "configuration is invalid") from None
