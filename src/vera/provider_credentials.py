"""Private, non-executable provider environment file handling."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Literal

from vera.config import ConfigurationError, UnsafeProviderEnvironment

_KEY_NAME = re.compile(r"[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET)\Z")
_LEGACY_SETTINGS = frozenset(
    {"VERA_DEEPSEEK_BASE_URL", "VERA_DEEPSEEK_MODEL", "VERA_GLM_BASE_URL", "VERA_GLM_MODEL"}
)


def provider_env_path() -> Path:
    return Path(
        os.environ.get(
            "VERA_PROVIDER_ENV_FILE", str(Path.home() / ".config" / "vera" / "deepseek.env")
        )
    )


def validate_key_name(name: str) -> None:
    if _KEY_NAME.fullmatch(name) is None:
        raise ConfigurationError("invalid_key_reference", "invalid provider key reference")


def _read_text(source: Path) -> str | None:
    try:
        if not source.exists() and not source.is_symlink():
            return None
        if source.is_symlink():
            raise UnsafeProviderEnvironment("provider environment path must be a regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(source, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise UnsafeProviderEnvironment("provider environment path must be a regular file")
            if os.name == "posix":
                if metadata.st_uid != os.getuid():
                    raise UnsafeProviderEnvironment(
                        "provider environment file must belong to current user"
                    )
                if stat.S_IMODE(metadata.st_mode) != 0o600:
                    raise UnsafeProviderEnvironment("provider environment file must use mode 0600")
            return handle.read()
    except UnsafeProviderEnvironment:
        raise
    except (OSError, UnicodeError) as exc:
        raise UnsafeProviderEnvironment("provider environment file cannot be read safely") from exc


def _parse(text: str, allowed_names: frozenset[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, separator, raw_value = line.partition("=")
        name = name.strip()
        if not separator or not (name in _LEGACY_SETTINGS or _KEY_NAME.fullmatch(name)):
            raise UnsafeProviderEnvironment(f"invalid provider setting at line {line_number}")
        if allowed_names is not None and name not in allowed_names:
            raise UnsafeProviderEnvironment(f"invalid provider setting at line {line_number}")
        if name in result:
            raise UnsafeProviderEnvironment(f"duplicate provider setting at line {line_number}")
        value = raw_value.strip()
        if any(token in value for token in ("`", "$(", "${", "\r", "\n")):
            raise UnsafeProviderEnvironment(f"shell syntax is forbidden at line {line_number}")
        if value.startswith(("'", '"')) or value.endswith(("'", '"')):
            if len(value) < 2 or value[0] != value[-1]:
                raise UnsafeProviderEnvironment(f"unmatched quote at line {line_number}")
            value = value[1:-1]
        result[name] = value
    return result


def read_provider_environment(
    allowed_names: frozenset[str], path: Path | None = None
) -> dict[str, str]:
    for name in allowed_names:
        if name not in _LEGACY_SETTINGS:
            validate_key_name(name)
    content = _read_text(path or provider_env_path())
    return {} if content is None else _parse(content, allowed_names)


def set_provider_key(name: str, value: str, path: Path | None = None) -> None:
    validate_key_name(name)
    if (
        not value
        or value != value.strip()
        or any(char in value for char in "\r\n`'\"")
        or "$(" in value
        or "${" in value
    ):
        raise ConfigurationError("invalid_provider_key", "provider key has invalid characters")
    source = path or provider_env_path()
    old = _read_text(source)
    values = _parse(old, None) if old is not None else {}
    values[name] = value
    try:
        source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".provider-env-", dir=source.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for field, saved in values.items():
                    handle.write(f"{field}={saved}\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, source)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except OSError as exc:
        raise ConfigurationError(
            "provider_key_write_failed", "private provider file cannot be updated"
        ) from exc


def key_status(
    name: str, file_values: dict[str, str]
) -> Literal["configured", "missing", "overridden_by_environment"]:
    if os.environ.get(name):
        return "overridden_by_environment" if file_values.get(name) else "configured"
    return "configured" if file_values.get(name) else "missing"
