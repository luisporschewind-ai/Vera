"""Trust ranking for content sources. Never grants instruction authority."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class ContentTrustLevel(StrEnum):
    BUILTIN_POLICY = "builtin_policy"
    USER_INTENT = "user_intent"
    ADVISORY = "advisory"
    UNTRUSTED = "untrusted"


SOURCE_USER_GOAL = "user_goal"
SOURCE_PROJECT_GUIDANCE = "project_guidance"
SOURCE_WORKSPACE_FILE = "workspace_file"
SOURCE_TOOL_OUTPUT = "tool_output"
SOURCE_CONVERSATION_SUMMARY = "conversation_summary"
SOURCE_MODEL_OUTPUT = "model_output"

_TRUST_RANK = {
    ContentTrustLevel.UNTRUSTED: 0,
    ContentTrustLevel.ADVISORY: 1,
    ContentTrustLevel.USER_INTENT: 2,
    ContentTrustLevel.BUILTIN_POLICY: 3,
}

_GUIDANCE_NAMES = frozenset(
    {
        "agents.md",
        "vera.md",
        "readme.md",
        "readme",
        "contributing.md",
        "code_of_conduct.md",
    }
)


def trust_rank(level: ContentTrustLevel) -> int:
    return _TRUST_RANK[level]


def default_trust_level(source_kind: str | None) -> ContentTrustLevel:
    if source_kind == SOURCE_USER_GOAL:
        return ContentTrustLevel.USER_INTENT
    if source_kind == SOURCE_PROJECT_GUIDANCE:
        return ContentTrustLevel.ADVISORY
    return ContentTrustLevel.UNTRUSTED


def lowest_trust(*levels: ContentTrustLevel) -> ContentTrustLevel:
    if not levels:
        return ContentTrustLevel.UNTRUSTED
    return min(levels, key=trust_rank)


def source_kind_for_path(relative_path: str) -> str:
    name = Path(relative_path).name.lower()
    if name in _GUIDANCE_NAMES:
        return SOURCE_PROJECT_GUIDANCE
    return SOURCE_WORKSPACE_FILE


def coerce_trust_level(
    requested: object,
    *,
    source_kind: str | None,
) -> ContentTrustLevel:
    ceiling = default_trust_level(source_kind)
    if not isinstance(requested, str):
        return ceiling
    try:
        candidate = ContentTrustLevel(requested)
    except ValueError:
        return ContentTrustLevel.UNTRUSTED
    if trust_rank(candidate) > trust_rank(ceiling):
        return ceiling
    return candidate


def normalize_origin(origin: str) -> str:
    text = origin.strip().replace("\\", "/")
    if not text:
        return "unknown"
    return text.lstrip("./") or "unknown"
