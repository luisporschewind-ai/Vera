"""Recursive redaction for secrets and sensitive field names."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from vera.contracts.events import EventEnvelope
from vera.contracts.streaming import RuntimeOutput, StreamFrame

_REDACTED = "[REDACTED]"
_SENSITIVE_FIELDS = frozenset(
    {
        "api_key",
        "authorization",
        "authorisation",
        "token",
        "password",
        "secret",
        "access_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
    }
)
_FORBIDDEN_ENV_EXACT = frozenset(
    {
        "AUTHORIZATION",
        "AUTHORISATION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AZURE_CLIENT_SECRET",
        "AZURE_CLIENT_ID",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "CIRCLE_TOKEN",
        "VERA_PROVIDER_ENV_FILE",
    }
)
_FORBIDDEN_ENV_PREFIXES = (
    "DEEPSEEK_",
    "GLM_",
    "OPENAI_",
    "ANTHROPIC_",
    "VERA_LIVE_",
    "VERA_DEEPSEEK_",
    "VERA_GLM_",
    "VERA_PROVIDER_",
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
)
_FORBIDDEN_ENV_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_ACCESS_KEY")
_BEARER_RE = re.compile(r"(?i)(\b(?:authorization\s*[:=]\s*)?bearer\s+)(\S+)")
_AUTHORIZATION_RE = re.compile(r"(?i)(\bauthorization\s*[:=]\s*)(?!bearer\b)(\S+)")
_QUERY_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|token|access[_-]?token|refresh[_-]?token|secret|password|"
    r"authorization)=)([^&\s#]+)"
)
_ENV_ASSIGN_RE = re.compile(
    r"(?i)\b([A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET|_PASSWORD)|AUTHORIZATION|"
    r"AUTHORISATION)\s*=\s*(\S+)"
)
_JSON_FIELD_RE = re.compile(
    r'(?i)("(?:api[_-]?key|authorization|authorisation|token|password|secret|'
    r'access[_-]?key|access[_-]?token|client[_-]?secret)"\s*:\s*")([^"]*)(")'
)
_VENDOR_KEY_RE = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|gho_[A-Za-z0-9]{8,}|"
    r"github_pat_[A-Za-z0-9_]{8,})\b"
)


@dataclass(frozen=True)
class SecretPolicy:
    sensitive_fields: frozenset[str] = _SENSITIVE_FIELDS
    forbidden_env_exact: frozenset[str] = _FORBIDDEN_ENV_EXACT
    forbidden_env_prefixes: tuple[str, ...] = _FORBIDDEN_ENV_PREFIXES
    forbidden_env_suffixes: tuple[str, ...] = _FORBIDDEN_ENV_SUFFIXES

    def is_sensitive_field(self, name: str) -> bool:
        normalized = name.strip().lower().replace("-", "_")
        if normalized in self.sensitive_fields:
            return True
        return any(normalized.endswith(f"_{field}") for field in self.sensitive_fields)

    def is_forbidden_env_name(self, name: str) -> bool:
        upper = name.strip().upper().replace("-", "_")
        if not upper:
            return True
        if upper in self.forbidden_env_exact:
            return True
        if any(upper.startswith(prefix) for prefix in self.forbidden_env_prefixes):
            return True
        return any(upper.endswith(suffix) for suffix in self.forbidden_env_suffixes)

    def redact_text(self, text: str, extra_secrets: Iterable[str] = ()) -> str:
        redacted = text
        for secret in sorted((value for value in extra_secrets if value), key=len, reverse=True):
            redacted = redacted.replace(secret, _REDACTED)
        redacted = _BEARER_RE.sub(rf"\1{_REDACTED}", redacted)
        redacted = _AUTHORIZATION_RE.sub(rf"\1{_REDACTED}", redacted)
        redacted = _QUERY_RE.sub(rf"\1{_REDACTED}", redacted)
        redacted = _ENV_ASSIGN_RE.sub(rf"\1={_REDACTED}", redacted)
        redacted = _JSON_FIELD_RE.sub(rf"\1{_REDACTED}\3", redacted)
        return _VENDOR_KEY_RE.sub(_REDACTED, redacted)

    def contains_secret(self, text: str) -> bool:
        return self.redact_text(text) != text


DEFAULT_SECRET_POLICY = SecretPolicy()


class Redactor:
    def __init__(
        self,
        secret_values: Iterable[str] = (),
        policy: SecretPolicy | None = None,
    ) -> None:
        self._policy = policy or DEFAULT_SECRET_POLICY
        self._secrets = tuple(
            sorted((value for value in secret_values if value), key=len, reverse=True)
        )

    def redact(self, value: Any) -> Any:
        if isinstance(value, BaseException):
            return self._policy.redact_text(f"{type(value).__name__}: {value}", self._secrets)
        if isinstance(value, dict):
            return {
                key: (_REDACTED if self._policy.is_sensitive_field(str(key)) else self.redact(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact(item) for item in value)
        if isinstance(value, str):
            return self._policy.redact_text(value, self._secrets)
        return value

    def redact_event(self, event: EventEnvelope) -> EventEnvelope:
        payload = self.redact(event.payload)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        return event.model_copy(update={"payload": payload})

    def redact_output(self, output: RuntimeOutput) -> RuntimeOutput:
        if isinstance(output, StreamFrame):
            payload = self.redact(output.payload)
            if not isinstance(payload, dict):
                payload = {"text": _REDACTED}
            return output.model_copy(update={"payload": payload})
        return self.redact_event(output)
