"""Bounded, provider-neutral research facts and tool inputs."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SECRET = re.compile(
    r"(?i)(?:api[_ -]?key|token|password|secret|authorization|bearer)\s*[:=]|"
    r"\b(?:sk-|ghp_|tvly-)[A-Za-z0-9_-]{8,}|-----BEGIN|\.env\b"
)
_PATH = re.compile(r"(?<!\w)(?:/Users/|/home/|[A-Za-z]:\\|~/)")
_DOMAIN = re.compile(r"(?i)(?:[a-z0-9-]+\.)+[a-z]{2,63}\Z")


class ResearchInputError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class WebSearchInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=4, max_length=200)
    preferred_domains: tuple[str, ...] = Field(default=(), max_length=3)
    max_results: int = Field(default=5, ge=1, le=5)

    @field_validator("query")
    @classmethod
    def public_query(cls, value: str) -> str:
        query = value.strip()
        if (
            len(query) < 4
            or len(query) > 200
            or any(ord(char) < 32 for char in query)
            or _SECRET.search(query)
            or _PATH.search(query)
            or any(char in query for char in ("`", "{", "}", ";"))
        ):
            raise ValueError("query_blocked")
        return query

    @field_validator("preferred_domains")
    @classmethod
    def valid_domains(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        domains = tuple(item.strip().lower() for item in value)
        if any(_DOMAIN.fullmatch(item) is None for item in domains):
            raise ValueError("invalid_preferred_domain")
        return domains


class WebReadResultInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str = Field(pattern=r"^query_[0-9a-f]{32}$")
    result_id: str = Field(pattern=r"^result_[0-9]{1,2}$")


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    result_id: str
    source_id: str
    canonical_url: str
    title: str
    snippet: str
    published_at: str | None = None


class SearchRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str
    query: str
    searched_at: datetime
    provider_id: str
    hits: tuple[SearchHit, ...]


class ResearchState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    searches: int = 0
    reads: int = 0
    output_bytes: int = 0
    records: tuple[SearchRecord, ...] = ()


def canonical_public_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        if parsed.scheme != "https" or host is None or parsed.username or parsed.password:
            return None
        if parsed.port not in {None, 443} or _DOMAIN.fullmatch(host) is None:
            return None
        if host.lower().endswith((".local", ".internal", ".test", ".localhost")):
            return None
        return urlunsplit(("https", host.lower(), parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None
