"""Layered, safety-bounded configuration for Vera."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from platformdirs import user_config_path, user_state_path
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class UnsafeProjectConfig(ValueError):
    """Raised when project configuration attempts to bypass a safety boundary."""


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_model_turns: int = Field(default=20, ge=1)
    max_tool_calls: int = Field(default=50, ge=1)
    max_file_bytes: int = Field(default=1_000_000, ge=1)
    max_tool_output_bytes: int = Field(default=100_000, ge=1)
    max_context_bytes: int = Field(default=2_000_000, ge=1)
    command_timeout_seconds: int = Field(default=120, ge=1)


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: AnyHttpUrl
    model: str
    api_key_env: str


class VeraConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state_dir: Path
    limits: Limits
    providers: dict[str, ProviderConfig]
    user_allowed_command_prefixes: tuple[tuple[str, ...], ...] = ()


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    workspace_root: Path
    goal_summary: str
    last_event_at: datetime
    terminal_state: str | None


_PROJECT_FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "user_allowed_command_prefixes",
    "allowed_command_prefixes",
    "safe_commands",
}


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    return value


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


def load_config(workspace: Path, cli_overrides: Mapping[str, object]) -> VeraConfig:
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
    merged["limits"] = _merge(merged.get("limits", {}), _env_limits())
    merged = _merge(merged, cli_overrides)
    state_dir = os.environ.get("VERA_STATE_DIR")
    if state_dir is not None:
        merged["state_dir"] = state_dir
    else:
        merged.setdefault("state_dir", str(user_state_path("Vera")))
    merged.setdefault("user_allowed_command_prefixes", ())
    return VeraConfig.model_validate(merged)
