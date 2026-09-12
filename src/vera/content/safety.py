"""Reserved, vendor-neutral content-safety interface. Not an authorization oracle."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from vera.content.envelope import ContentEnvelope

SAFETY_POLICY_VERSION = "s1-not-enforced"


class ContentSafetyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["allow", "review", "refuse"]
    reason_code: str
    category: str | None = None
    policy_version: str = SAFETY_POLICY_VERSION


class ContentSafetyPolicy(Protocol):
    def assess(self, envelope: ContentEnvelope) -> ContentSafetyDecision: ...


class AllowAllContentSafetyPolicy:
    """Phase-5 placeholder: no public content policy is enforced yet."""

    def assess(self, envelope: ContentEnvelope) -> ContentSafetyDecision:
        del envelope
        return ContentSafetyDecision(decision="allow", reason_code="not_enforced")
