"""RetryPolicy matrix tests."""

import pytest

from vera.models.errors import ModelErrorCode, ModelProviderError
from vera.models.retry import RetryPolicy


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        (ModelErrorCode.NETWORK, None, True),
        (ModelErrorCode.TIMEOUT, None, True),
        (ModelErrorCode.RATE_LIMITED, 429, True),
        (ModelErrorCode.SERVICE, 503, True),
        (ModelErrorCode.SERVICE, 400, False),
        (ModelErrorCode.AUTHENTICATION, 401, False),
        (ModelErrorCode.INVALID_RESPONSE, None, False),
    ],
)
def test_retry_matrix(code, status, expected) -> None:
    error = ModelProviderError(code=code, message="safe", status_code=status)
    assert RetryPolicy(max_attempts=2).should_retry(error, attempt=1) is expected
    assert RetryPolicy(max_attempts=2).should_retry(error, attempt=2) is False


def test_retry_after_is_capped() -> None:
    policy = RetryPolicy(max_attempts=2, max_delay_seconds=2.0)
    short = ModelProviderError(
        ModelErrorCode.RATE_LIMITED, "safe", retry_after_seconds=0.5, status_code=429
    )
    long = ModelProviderError(
        ModelErrorCode.RATE_LIMITED, "safe", retry_after_seconds=60, status_code=429
    )
    assert policy.delay_seconds(short, 1) == 0.5
    assert policy.delay_seconds(long, 1) == 2.0
