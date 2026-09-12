"""Construct child-process environments from an empty baseline and allowlist."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from vera.redaction import DEFAULT_SECRET_POLICY

_LOCALE_AND_TERM = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_NUMERIC",
        "LC_TIME",
        "LC_COLLATE",
        "LC_MONETARY",
        "TZ",
        "TERM",
        "TERM_PROGRAM",
        "COLORTERM",
        "TMPDIR",
        "TMP",
        "TEMP",
    }
)
_EVAL_TASK_VARS = frozenset(
    {
        "HOME",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONNOUSERSITE",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
    }
)


@dataclass(frozen=True)
class ChildEnvironment:
    values: dict[str, str]
    inherited: tuple[str, ...]
    denied: tuple[str, ...]
    purpose: str


def is_forbidden_environment_name(name: str) -> bool:
    return DEFAULT_SECRET_POLICY.is_forbidden_env_name(name)


def _allowlist_for(purpose: str) -> frozenset[str]:
    if purpose == "eval_worker":
        return _LOCALE_AND_TERM | _EVAL_TASK_VARS
    return _LOCALE_AND_TERM


def _is_allowlisted(name: str, allowlist: frozenset[str]) -> bool:
    upper = name.upper()
    return name in allowlist or any(upper == item.upper() for item in allowlist)


def build_child_environment(
    overrides: Mapping[str, str] | None = None,
    purpose: str = "verification",
    *,
    source: Mapping[str, str] | None = None,
    extra_allow_names: Iterable[str] = (),
) -> ChildEnvironment:
    """Build a child env from a blank baseline, allowlist, then filtered overrides."""

    if source is None:
        import os

        source = os.environ
    allowlist = _allowlist_for(purpose) | frozenset(extra_allow_names)
    values: dict[str, str] = {}
    inherited: list[str] = []
    denied: list[str] = []
    seen_denied: set[str] = set()

    def deny(name: str) -> None:
        marker = name.upper()
        if marker in seen_denied:
            return
        seen_denied.add(marker)
        denied.append(name)

    source_by_upper = {key.upper(): (key, value) for key, value in source.items()}
    for key, value in source.items():
        if is_forbidden_environment_name(key):
            deny(key)
            continue
        if _is_allowlisted(key, allowlist):
            values[key] = value
            inherited.append(key)

    for name in extra_allow_names:
        if is_forbidden_environment_name(name):
            deny(name)
            continue
        match = source_by_upper.get(name.upper())
        if match is None:
            continue
        source_key, source_value = match
        if is_forbidden_environment_name(source_key):
            deny(source_key)
            continue
        if source_key not in values:
            values[source_key] = source_value
            inherited.append(source_key)

    for key, value in dict(overrides or {}).items():
        if is_forbidden_environment_name(key):
            deny(key)
            values.pop(key, None)
            for existing in list(values):
                if existing.upper() == key.upper():
                    values.pop(existing, None)
            continue
        values[key] = value

    return ChildEnvironment(
        values=values,
        inherited=tuple(inherited),
        denied=tuple(denied),
        purpose=purpose,
    )
