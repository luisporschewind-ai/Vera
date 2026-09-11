"""Model error payload safety tests."""

from vera.models.errors import ModelErrorCode, ModelProviderError, safe_error_payload


def test_provider_error_never_exposes_cause_text() -> None:
    error = ModelProviderError(
        code=ModelErrorCode.AUTHENTICATION,
        message="provider authentication failed",
        status_code=401,
    )
    assert error.retryable is False
    assert "secret" not in str(error).lower()
    payload = safe_error_payload(error, 1)
    assert payload["code"] == "provider_authentication_error"
    assert "secret" not in str(payload).lower()
