"""Core service for the user's non-secret model profile choices."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict

from vera.config import ConfigurationError, ProviderConfig
from vera.provider_catalog import CATALOG_BY_ID, MODEL_CATALOG


class ProfileSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str
    provider_id: str
    display_name: str
    model_id: str
    base_url: str | None
    api_key_env: str
    enabled: bool
    position: int
    default: bool
    valid: bool
    reason: str | None = None
    key_status: str = "missing"


class ProviderConfigurationService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(
            os.environ.get(
                "VERA_MODEL_PROFILES_FILE",
                str(user_config_path("Vera") / "model_profiles.json"),
            )
        )

    def _read(self) -> dict[str, Any]:
        if not self.path.exists() and not self.path.is_symlink():
            return {
                "version": 1,
                "enabled": [],
                "order": [],
                "default": None,
                "custom_profiles": {},
                "overrides": {},
                "catalog_snapshot": {},
            }
        try:
            mode = self.path.lstat().st_mode
            if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                raise ValueError("managed profile path is not regular")
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("unsupported managed profile version")
            enabled = raw.get("enabled", [])
            order = raw.get("order", [])
            custom = raw.get("custom_profiles", {})
            overrides = raw.get("overrides", {})
            snapshot = raw.get("catalog_snapshot", {})
            default = raw.get("default")
            if set(raw) - {
                "version",
                "enabled",
                "order",
                "default",
                "custom_profiles",
                "overrides",
                "catalog_snapshot",
            }:
                raise ValueError("unknown managed profile field")
            if (
                not isinstance(enabled, list)
                or not isinstance(order, list)
                or not isinstance(custom, dict)
                or not isinstance(overrides, dict)
                or not isinstance(snapshot, dict)
            ):
                raise ValueError("invalid managed profile shape")
            for key, value in snapshot.items():
                if (
                    not isinstance(key, str)
                    or not key
                    or not isinstance(value, dict)
                    or set(value) != {"provider_id", "display_name", "model_id", "api_key_env"}
                    or any(not isinstance(field, str) or not field for field in value.values())
                ):
                    raise ValueError("invalid catalog snapshot")
            known = set(CATALOG_BY_ID) | set(custom) | set(snapshot)
            if any(not isinstance(x, str) or x not in known for x in enabled + order):
                raise ValueError("unknown profile reference")
            if len(set(enabled)) != len(enabled) or len(set(order)) != len(order):
                raise ValueError("duplicate profile reference")
            if default is not None and (not isinstance(default, str) or default not in enabled):
                raise ValueError("default profile must be enabled")
            for key, value in custom.items():
                if not isinstance(key, str) or key in CATALOG_BY_ID or not isinstance(value, dict):
                    raise ValueError("invalid custom profile")
                ProviderConfig.model_validate(value)
            for key, value in overrides.items():
                if key not in CATALOG_BY_ID and key not in snapshot or not isinstance(value, dict):
                    raise ValueError("invalid catalog override")
                ProviderConfig.model_validate(value)
            return raw
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            raise ConfigurationError(
                "invalid_model_profiles", "user model profile file is invalid"
            ) from None

    def _write(self, data: dict[str, Any]) -> None:
        snapshot = dict(data.get("catalog_snapshot", {}))
        snapshot.update(
            {
                item.profile_id: {
                    "provider_id": item.provider_id,
                    "display_name": item.display_name,
                    "model_id": item.model_id,
                    "api_key_env": item.api_key_env,
                }
                for item in MODEL_CATALOG
            }
        )
        data["catalog_snapshot"] = snapshot
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".model_profiles-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _all_configs(self, data: dict[str, Any]) -> dict[str, ProviderConfig | None]:
        result: dict[str, ProviderConfig | None] = {}
        for item in MODEL_CATALOG:
            override = data.get("overrides", {}).get(item.profile_id)
            result[item.profile_id] = (
                ProviderConfig.model_validate(override) if override else item.provider_config()
            )
        for profile_id, raw in data.get("custom_profiles", {}).items():
            result[profile_id] = ProviderConfig.model_validate(raw)
        for profile_id in data.get("catalog_snapshot", {}):
            result.setdefault(profile_id, None)
        return result

    def list_profiles(self) -> tuple[ProfileSummary, ...]:
        data = self._read()
        configs = self._all_configs(data)
        preferred = list(data["order"]) + [name for name in configs if name not in data["order"]]
        order = [name for name in preferred if name in data["enabled"]] + [
            name for name in preferred if name not in data["enabled"]
        ]
        result: list[ProfileSummary] = []
        for position, profile_id in enumerate(order):
            entry = CATALOG_BY_ID.get(profile_id)
            retired = data.get("catalog_snapshot", {}).get(profile_id, {})
            config = configs[profile_id]
            result.append(
                ProfileSummary(
                    profile_id=profile_id,
                    provider_id=entry.provider_id
                    if entry
                    else retired.get("provider_id", "custom"),
                    display_name=entry.display_name
                    if entry
                    else retired.get("display_name", profile_id),
                    model_id=config.model
                    if config
                    else entry.model_id
                    if entry
                    else retired.get("model_id", ""),
                    base_url=str(config.base_url) if config else None,
                    api_key_env=config.api_key_env
                    if config
                    else entry.api_key_env
                    if entry
                    else retired.get("api_key_env", ""),
                    enabled=profile_id in data["enabled"],
                    position=position,
                    default=profile_id == data["default"],
                    valid=config is not None,
                    reason=None
                    if config is not None
                    else (
                        "catalog_unavailable" if retired and entry is None else "endpoint_required"
                    ),
                )
            )
        return tuple(result)

    def list_profiles_with_keys(
        self, legacy: dict[str, ProviderConfig] | None = None
    ) -> tuple[ProfileSummary, ...]:
        from vera.provider_credentials import (
            key_status,
            read_provider_environment,
        )

        legacy = legacy or {}
        summaries = list(self.list_profiles())
        for profile_id, config in legacy.items():
            if any(item.profile_id == profile_id for item in summaries):
                continue
            summaries.append(
                ProfileSummary(
                    profile_id=profile_id,
                    provider_id="custom",
                    display_name=profile_id,
                    model_id=config.model,
                    base_url=str(config.base_url),
                    api_key_env=config.api_key_env,
                    enabled=True,
                    position=len(summaries),
                    default=False,
                    valid=True,
                )
            )
        names = frozenset(item.api_key_env for item in summaries) | frozenset(
            {
                "VERA_DEEPSEEK_BASE_URL",
                "VERA_DEEPSEEK_MODEL",
                "VERA_GLM_BASE_URL",
                "VERA_GLM_MODEL",
            }
        )
        file_values = read_provider_environment(names)
        result: list[ProfileSummary] = []
        for item in summaries:
            status = key_status(item.api_key_env, file_values)
            reason = item.reason
            if item.enabled and item.valid and status == "missing":
                reason = "missing_key"
            result.append(item.model_copy(update={"key_status": status, "reason": reason}))
        return tuple(result)

    def effective_providers(self, legacy: dict[str, ProviderConfig]) -> dict[str, ProviderConfig]:
        data = self._read()
        managed_names = (
            set(CATALOG_BY_ID)
            | set(data["custom_profiles"])
            | set(data.get("catalog_snapshot", {}))
        )
        result = (
            {name: config for name, config in legacy.items() if name not in managed_names}
            if self.path.exists()
            else dict(legacy)
        )
        result.update(
            {
                name: config
                for name, config in self._all_configs(data).items()
                if config is not None and name in data["enabled"]
            }
        )
        return result

    def enabled_profiles(self) -> tuple[str, ...]:
        return tuple(
            item.profile_id for item in self.list_profiles() if item.enabled and item.valid
        )

    def default_profile(self) -> str | None:
        value = self._read()["default"]
        return value if isinstance(value, str) else None

    def _require_known(self, data: dict[str, Any], profile_id: str) -> None:
        if profile_id not in CATALOG_BY_ID and profile_id not in data["custom_profiles"]:
            raise ConfigurationError("unknown_model_profile", "model profile is unknown")

    def enable(self, profile_id: str) -> None:
        data = self._read()
        self._require_known(data, profile_id)
        if self._all_configs(data)[profile_id] is None:
            raise ConfigurationError("endpoint_required", "model endpoint must be selected")
        if profile_id not in data["enabled"]:
            data["enabled"].append(profile_id)
        self._write(data)

    def disable(self, profile_id: str) -> None:
        data = self._read()
        self._require_known(data, profile_id)
        if data["default"] == profile_id:
            raise ConfigurationError(
                "default_model_profile", "select a new default before disabling"
            )
        data["enabled"] = [name for name in data["enabled"] if name != profile_id]
        self._write(data)

    def move_before(self, profile_id: str, other_id: str) -> None:
        data = self._read()
        self._require_known(data, profile_id)
        self._require_known(data, other_id)
        order = [item.profile_id for item in self.list_profiles() if item.profile_id != profile_id]
        order.insert(order.index(other_id), profile_id)
        data["order"] = order
        self._write(data)

    def set_default(self, profile_id: str) -> None:
        data = self._read()
        self._require_known(data, profile_id)
        if profile_id not in data["enabled"]:
            raise ConfigurationError(
                "model_profile_disabled", "enable the model before selecting it"
            )
        data["default"] = profile_id
        self._write(data)

    def add_custom(self, profile: ProviderConfig, profile_id: str) -> None:
        data = self._read()
        if (
            re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", profile_id) is None
            or profile_id in CATALOG_BY_ID
            or profile_id in data["custom_profiles"]
            or profile_id in data.get("catalog_snapshot", {})
        ):
            raise ConfigurationError("duplicate_model_profile", "profile identifier is unavailable")
        data["custom_profiles"][profile_id] = profile.model_dump(mode="json")
        self._write(data)

    def configure_catalog(self, profile_id: str, profile: ProviderConfig) -> None:
        data = self._read()
        if profile_id not in CATALOG_BY_ID:
            raise ConfigurationError("unknown_model_profile", "catalog profile is unknown")
        data["overrides"][profile_id] = profile.model_dump(mode="json")
        self._write(data)
