"""Bounded security findings for a run. Advisory facts only."""

from __future__ import annotations

from vera.content.detector import (
    ContentDetection,
    DetectionDisposition,
    event_security_summary,
)
from vera.content.envelope import (
    EMPTY_SECURITY_CONTEXT_HASH,
    ContentEnvelope,
    ContentFinding,
    compute_security_context_hash,
)

MAX_SECURITY_FINDINGS = 64

_DISPOSITION_RANK = {
    DetectionDisposition.CLEAR.value: 0,
    DetectionDisposition.WARN.value: 1,
    DetectionDisposition.QUARANTINE.value: 2,
    DetectionDisposition.BLOCK.value: 3,
    DetectionDisposition.UNAVAILABLE.value: 3,
}


def finding_key(envelope: ContentEnvelope) -> tuple[str, str, str]:
    return (envelope.content_hash, envelope.source_kind, envelope.origin)


def merge_finding(
    findings: tuple[ContentFinding, ...],
    envelope: ContentEnvelope,
    detection: ContentDetection,
) -> tuple[tuple[ContentFinding, ...], bool]:
    key = finding_key(envelope)
    if any(finding_key(item.envelope) == key for item in findings):
        return findings, False
    finding = ContentFinding(
        envelope=envelope,
        disposition=detection.disposition.value,
        reason_code=detection.reason_code,
        detector_version=detection.detector_version,
    )
    return (*findings, finding), True


def worst_disposition(findings: tuple[ContentFinding, ...]) -> str | None:
    if not findings:
        return None
    return max(findings, key=lambda item: _DISPOSITION_RANK.get(item.disposition, 2)).disposition


def collected_risk_labels(findings: tuple[ContentFinding, ...]) -> tuple[str, ...]:
    labels: list[str] = []
    for finding in findings:
        labels.extend(finding.envelope.risk_labels)
    return tuple(dict.fromkeys(labels))


def security_payload(envelope: ContentEnvelope, detection: ContentDetection) -> dict[str, object]:
    return event_security_summary(envelope, detection)


def current_security_hash(findings: tuple[ContentFinding, ...]) -> str:
    if not findings:
        return EMPTY_SECURITY_CONTEXT_HASH
    return compute_security_context_hash(findings)
