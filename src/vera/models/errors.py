"""Normalized provider errors safe for Event payloads."""

from __future__ import annotations

from enum import StrEnum

from vera.contracts import JsonValue


class ModelErrorCode(StrEnum):
    CONFIGURATION = "provider_configuration_error"
    AUTHENTICATION = "provider_authentication_error"
    NETWORK = "provider_network_error"
    TIMEOUT = "provider_timeout"
    RATE_LIMITED = "provider_rate_limited"
    SERVICE = "provider_service_error"
    REQUEST_INVALID = "provider_request_invalid"
    INVALID_RESPONSE = "provider_invalid_response"
    CAPABILITY_MISMATCH = "capability_mismatch"


class ModelProviderError(Exception):
    def __init__(
        self,
        code: ModelErrorCode,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code
        self.request_id = request_id
        self.detail = detail

    @property
    def retryable(self) -> bool:
        if self.code in {
            ModelErrorCode.NETWORK,
            ModelErrorCode.TIMEOUT,
            ModelErrorCode.RATE_LIMITED,
        }:
            return True
        if self.code is ModelErrorCode.SERVICE and self.status_code is not None:
            return self.status_code >= 500
        return False


def safe_error_payload(error: ModelProviderError, attempt: int) -> dict[str, JsonValue]:
    return {
        "code": error.code.value,
        "message": error.message,
        "attempt": attempt,
        "status_code": error.status_code,
        "request_id": error.request_id,
        "retry_after_seconds": error.retry_after_seconds,
        "detail": error.detail,
    }
