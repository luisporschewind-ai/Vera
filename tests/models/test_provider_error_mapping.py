from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

from vera.config import ProviderConfig
from vera.models.errors import ModelErrorCode, safe_error_payload
from vera.models.openai_compatible import OpenAICompatibleAdapter


def adapter() -> OpenAICompatibleAdapter:
    """Mapping is pure, so an inert client keeps the test off the network."""

    completions = SimpleNamespace(create=lambda **_: None)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAICompatibleAdapter(
        ProviderConfig(
            base_url="https://api.example.test/v1",  # type: ignore[arg-type]
            model="fake-model",
            api_key_env="FAKE_API_KEY",
        ),
        client=client,
    )


def status_error(status_code: int, body: object) -> APIStatusError:
    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    response = httpx.Response(status_code, request=request, json=body)
    return APIStatusError("request failed", response=response, body=body)


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (400, ModelErrorCode.REQUEST_INVALID, False),
        (404, ModelErrorCode.REQUEST_INVALID, False),
        (500, ModelErrorCode.SERVICE, True),
        (503, ModelErrorCode.SERVICE, True),
    ],
)
def test_client_and_server_errors_map_to_distinct_codes(
    status_code: int, expected_code: ModelErrorCode, retryable: bool
) -> None:
    exc = status_error(status_code, {"error": {"message": "context length exceeded"}})
    mapped = adapter()._map_exception(exc)
    assert mapped.code is expected_code
    assert mapped.status_code == status_code
    assert mapped.retryable is retryable


def test_provider_reason_is_preserved_for_diagnosis() -> None:
    exc = status_error(400, {"error": {"message": "This model's maximum context length is 65536"}})
    mapped = adapter()._map_exception(exc)
    assert mapped.detail is not None
    assert "maximum context length" in mapped.detail
    payload = safe_error_payload(mapped, attempt=1)
    assert payload["status_code"] == 400
    assert payload["code"] == "provider_request_invalid"
    assert "maximum context length" in str(payload["detail"])


def test_detail_is_collapsed_and_bounded() -> None:
    exc = status_error(400, {"error": {"message": "a\n\n" + "b" * 500}})
    mapped = adapter()._map_exception(exc)
    assert mapped.detail is not None
    assert "\n" not in mapped.detail
    assert len(mapped.detail) <= 200


def test_missing_body_falls_back_without_crashing() -> None:
    exc = status_error(418, {"unexpected": True})
    mapped = adapter()._map_exception(exc)
    assert mapped.code is ModelErrorCode.REQUEST_INVALID
    assert mapped.retryable is False
