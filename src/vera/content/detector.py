"""Local, replaceable prompt-injection detector. Never an authorization oracle."""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from enum import StrEnum
from typing import Protocol

from vera.content.envelope import ContentEnvelope
from vera.content.trust import ContentTrustLevel
from vera.contracts import ContractModel

DETECTOR_VERSION = "baseline-s1"
MAX_ASSESS_CHARS = 200_000
MAX_BASE64_MATCHES = 32
MAX_BASE64_TOKEN_CHARS = 4_096
MAX_BASE64_DECODE_BYTES = 4_096

KNOWN_RISK_LABELS = frozenset(
    {
        "instruction_override",
        "prompt_exfiltration",
        "secret_exfiltration",
        "outbound_exfiltration",
        "destructive_command",
        "auto_execute",
        "hidden_instruction",
        "obfuscated_payload",
    }
)


class DetectionDisposition(StrEnum):
    CLEAR = "clear"
    WARN = "warn"
    QUARANTINE = "quarantine"
    BLOCK = "block"
    UNAVAILABLE = "unavailable"


class ContentDetection(ContractModel):
    schema_version: int = 1
    disposition: DetectionDisposition
    risk_labels: tuple[str, ...] = ()
    reason_code: str
    detector_version: str


class ContentDetector(Protocol):
    def assess(self, envelope: ContentEnvelope, text: str) -> ContentDetection: ...


_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
_BASE64_TOKEN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/])")
_HIDDEN_MARKUP = re.compile(
    r"<!--.*?-->|<span[^>]*display\s*:\s*none[^>]*>.*?</span>",
    re.IGNORECASE | re.DOTALL,
)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"ignore (all )?(previous|prior|above|system) (instructions|rules|policies)|"
            r"忽略(所有)?(之前|先前|以上|系统)(的)?(指令|规则|策略)|"
            r"you are now (?:the |an )?(?:unrestricted|jailbroken|root)",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"(reveal|disclose|print|leak) (the )?(system prompt|hidden instructions)|"
            r"泄露(系统提示|隐藏指令)",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"(exfiltrate|send|upload|post).{0,80}(api[_-]?key|secret|token|password)|"
            r"把(秘密|密钥|凭据|token|api.?key)发到外部",
            re.IGNORECASE,
        ),
    ),
    (
        "outbound_exfiltration",
        re.compile(r"\b(curl|wget|nc|ncat)\b.{0,160}https?://", re.IGNORECASE),
    ),
    (
        "destructive_command",
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b", re.IGNORECASE),
    ),
    (
        "auto_execute",
        re.compile(
            r"(自动执行|automatically execute|auto[- ]run).{0,40}(readme|agents\.md|命令|command)|"
            r"(按|根据|follow|obey).{0,20}(readme|agents\.md).{0,20}"
            r"(自动执行|execute|command|命令|instruction)",
            re.IGNORECASE,
        ),
    ),
)


def event_security_summary(
    envelope: ContentEnvelope,
    detection: ContentDetection,
) -> dict[str, object]:
    return {
        "content_hash": envelope.content_hash,
        "detector_version": detection.detector_version,
        "disposition": detection.disposition.value,
        "origin": envelope.origin,
        "reason_code": detection.reason_code,
        "risk_labels": list(detection.risk_labels),
        "source_kind": envelope.source_kind,
        "trust_level": envelope.trust_level.value,
        "schema_version": envelope.schema_version,
    }


class BaselinePromptInjectionDetector:
    def assess(self, envelope: ContentEnvelope, text: str) -> ContentDetection:
        if envelope.trust_level is ContentTrustLevel.BUILTIN_POLICY:
            return ContentDetection(
                disposition=DetectionDisposition.CLEAR,
                reason_code="builtin_policy",
                detector_version=DETECTOR_VERSION,
            )
        sample = text if len(text) <= MAX_ASSESS_CHARS else text[:MAX_ASSESS_CHARS]
        normalized = _normalize(sample)
        labels = _collect_labels(normalized)
        if not labels:
            return ContentDetection(
                disposition=DetectionDisposition.CLEAR,
                reason_code="no_injection_signal",
                detector_version=DETECTOR_VERSION,
            )
        severe = {"secret_exfiltration", "outbound_exfiltration", "destructive_command"}
        if severe.intersection(labels):
            disposition = DetectionDisposition.BLOCK
        elif "obfuscated_payload" in labels or "hidden_instruction" in labels:
            disposition = DetectionDisposition.QUARANTINE
        else:
            disposition = DetectionDisposition.WARN
        return ContentDetection(
            disposition=disposition,
            risk_labels=tuple(labels),
            reason_code="prompt_injection_suspected",
            detector_version=DETECTOR_VERSION,
        )


class SafeContentDetector:
    """Adapter: detector faults become UNAVAILABLE, never CLEAR."""

    def __init__(self, inner: ContentDetector) -> None:
        self._inner = inner

    def assess(self, envelope: ContentEnvelope, text: str) -> ContentDetection:
        try:
            result = self._inner.assess(envelope, text)
        except Exception:
            return _unavailable("detector_error")
        if not isinstance(result, ContentDetection):
            return _unavailable("detector_invalid_result")
        try:
            DetectionDisposition(result.disposition)
        except ValueError:
            return _unavailable("detector_invalid_disposition")
        labels = tuple(str(label) for label in result.risk_labels)
        if any(not label for label in labels):
            return _unavailable("detector_invalid_result")
        return result


def _unavailable(reason_code: str) -> ContentDetection:
    return ContentDetection(
        disposition=DetectionDisposition.UNAVAILABLE,
        risk_labels=("detector_unavailable",),
        reason_code=reason_code,
        detector_version="unavailable",
    )


def _collect_labels(normalized: str) -> list[str]:
    labels: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(normalized):
            labels.append(label)
    if _HIDDEN_MARKUP.search(normalized) and any(
        item in labels for item in ("instruction_override", "auto_execute", "secret_exfiltration")
    ):
        labels.append("hidden_instruction")
    if "obfuscated_payload" not in labels and _looks_obfuscated(normalized) and labels:
        labels.append("obfuscated_payload")
    return list(dict.fromkeys(labels))


def _looks_obfuscated(normalized: str) -> bool:
    return bool(_BASE64_TOKEN.search(normalized)) and "ignore previous" in normalized.lower()


def _normalize(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text)
    stripped = _ZERO_WIDTH.sub(" ", nfkc)
    decoded = _bounded_base64_plaintexts(stripped)
    extra = "\n".join(decoded)
    return f"{stripped}\n{extra}" if extra else stripped


def _bounded_base64_plaintexts(text: str) -> list[str]:
    found: list[str] = []
    for match in _BASE64_TOKEN.finditer(text):
        if len(found) >= MAX_BASE64_MATCHES:
            break
        token = match.group(0)
        if len(token) > MAX_BASE64_TOKEN_CHARS:
            continue
        padded = token + ("=" * ((4 - len(token) % 4) % 4))
        try:
            raw = base64.b64decode(padded, validate=True)
        except (ValueError, binascii.Error):
            continue
        if len(raw) > MAX_BASE64_DECODE_BYTES:
            raw = raw[:MAX_BASE64_DECODE_BYTES]
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if decoded.isprintable() or "\n" in decoded:
            found.append(unicodedata.normalize("NFKC", decoded))
    return found
