"""Bounded retry decisions for transient model failures."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from vera.models.errors import ModelProviderError


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_attempts: int = Field(default=2, ge=1)
    base_delay_seconds: float = Field(default=0.25, ge=0.0)
    max_delay_seconds: float = Field(default=2.0, ge=0.0)

    def should_retry(self, error: ModelProviderError, attempt: int) -> bool:
        if attempt >= self.max_attempts:
            return False
        return error.retryable

    def delay_seconds(self, error: ModelProviderError, attempt: int) -> float:
        if error.retry_after_seconds is not None:
            return float(min(max(error.retry_after_seconds, 0.0), self.max_delay_seconds))
        delay = self.base_delay_seconds * (2 ** max(attempt - 1, 0))
        return float(min(delay, self.max_delay_seconds))
