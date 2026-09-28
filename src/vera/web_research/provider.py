"""Fixed-host Tavily adapter behind a small Core-owned provider interface."""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from vera.web_research.contracts import canonical_public_url


class WebResearchProviderError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class WebResearchProvider(Protocol):
    provider_id: str
    external_target: str

    def search(
        self, query: str, *, domains: tuple[str, ...], max_results: int
    ) -> list[dict[str, Any]]: ...

    def extract(self, url: str) -> str: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class TavilyProvider:
    provider_id = "tavily"
    external_target = "api.tavily.com"
    _base = "https://api.tavily.com"

    def __init__(self, api_key: str | None, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._opener = build_opener(_NoRedirect())

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def search(
        self, query: str, *, domains: tuple[str, ...], max_results: int
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "/search",
            {
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_domains": list(domains),
                "include_raw_content": False,
            },
        )
        results = payload.get("results")
        if not isinstance(results, list):
            raise WebResearchProviderError("source_unavailable")
        return [item for item in results if isinstance(item, dict)]

    def extract(self, url: str) -> str:
        payload = self._request(
            "/extract", {"urls": [url], "extract_depth": "basic", "format": "markdown"}
        )
        results = payload.get("results")
        if not isinstance(results, list):
            raise WebResearchProviderError("source_unavailable")
        for item in results:
            if isinstance(item, dict) and canonical_public_url(item.get("url")) == url:
                content = item.get("raw_content")
                if isinstance(content, str) and content.strip():
                    return content
        raise WebResearchProviderError("source_unavailable")

    def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise WebResearchProviderError("search_provider_unconfigured")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            self._base + endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                if response.status != 200:
                    raise WebResearchProviderError("source_unavailable")
                raw = response.read(1_000_001)
        except HTTPError as exc:
            if exc.code == 429:
                raise WebResearchProviderError("rate_limited") from exc
            if exc.code in {432, 433}:
                raise WebResearchProviderError("quota_exceeded") from exc
            raise WebResearchProviderError("source_unavailable") from exc
        except TimeoutError as exc:
            raise WebResearchProviderError("search_timeout") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise WebResearchProviderError("search_timeout") from exc
            raise WebResearchProviderError("network_unavailable") from exc
        except OSError as exc:
            raise WebResearchProviderError("network_unavailable") from exc
        if len(raw) > 1_000_000:
            raise WebResearchProviderError("source_unavailable")
        try:
            decoded = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise WebResearchProviderError("source_unavailable") from exc
        if not isinstance(decoded, dict):
            raise WebResearchProviderError("source_unavailable")
        return decoded
