"""Run-bound budgets, normalization and source binding for web research."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from vera.tools.definitions import ToolResult
from vera.web_research.contracts import (
    SearchHit,
    SearchRecord,
    WebReadResultInput,
    WebSearchInput,
    canonical_public_url,
)
from vera.web_research.provider import WebResearchProvider, WebResearchProviderError
from vera.web_research.store import ResearchStore, ResearchStoreError

_MAX_SEARCHES = 3
_MAX_READS = 5
_MAX_TOTAL_BYTES = 40_960
_MAX_EXCERPT_BYTES = 8_192


def _bounded_text(value: object, max_bytes: int) -> tuple[str, bool]:
    if not isinstance(value, str):
        return "", False
    encoded = value.strip().encode("utf-8")
    if len(encoded) <= max_bytes:
        return encoded.decode("utf-8"), False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


class WebResearchService:
    def __init__(self, provider: WebResearchProvider, store: ResearchStore) -> None:
        self.provider = provider
        self.store = store

    def search(self, run_id: str, arguments: WebSearchInput) -> ToolResult:
        if getattr(self.provider, "configured", True) is False:
            return ToolResult(ok=False, error_code="search_provider_unconfigured")
        try:
            state = self.store.load(run_id)
            if state.searches >= _MAX_SEARCHES or state.output_bytes >= _MAX_TOTAL_BYTES:
                return ToolResult(ok=False, error_code="quota_exceeded")
            # Charge before the request: a timeout or crash must not silently retry a billed search.
            self.store.save(run_id, state.model_copy(update={"searches": state.searches + 1}))
            raw_hits = self.provider.search(
                arguments.query,
                domains=arguments.preferred_domains,
                max_results=arguments.max_results,
            )
        except (ResearchStoreError, WebResearchProviderError) as exc:
            return ToolResult(ok=False, error_code=str(exc))
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for raw in raw_hits:
            url = canonical_public_url(raw.get("url"))
            if url is None or url in seen:
                continue
            seen.add(url)
            title, _ = _bounded_text(raw.get("title"), 120)
            snippet, _ = _bounded_text(raw.get("content"), 400)
            published, _ = _bounded_text(raw.get("published_date"), 40)
            source_seed = f"{self.provider.provider_id}:{url}:{snippet}".encode()
            hits.append(
                SearchHit(
                    result_id=f"result_{len(hits) + 1}",
                    source_id="source_" + hashlib.sha256(source_seed).hexdigest()[:16],
                    canonical_url=url,
                    title=title or url,
                    snippet=snippet,
                    published_at=published or None,
                )
            )
            if len(hits) >= arguments.max_results:
                break
        if not hits:
            return ToolResult(ok=False, error_code="no_results")
        searched_at = datetime.now(UTC)
        query_id = "query_" + uuid4().hex
        content: dict[str, object] = {
            "query_id": query_id,
            "searched_at": searched_at.isoformat(),
            "provider_id": self.provider.provider_id,
            "results": [
                {
                    **hit.model_dump(mode="json"),
                    "source_type": "unverified",
                    "evidence_level": "search_snippet",
                }
                for hit in hits
            ],
        }
        byte_count = len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
        if state.output_bytes + byte_count > _MAX_TOTAL_BYTES:
            return ToolResult(ok=False, error_code="quota_exceeded")
        record = SearchRecord(
            query_id=query_id,
            query=arguments.query,
            searched_at=searched_at,
            provider_id=self.provider.provider_id,
            hits=tuple(hits),
        )
        try:
            self.store.save(
                run_id,
                state.model_copy(
                    update={
                        "searches": state.searches + 1,
                        "output_bytes": state.output_bytes + byte_count,
                        "records": (*state.records, record),
                    }
                ),
            )
        except ResearchStoreError as exc:
            return ToolResult(ok=False, error_code=str(exc))
        return ToolResult(ok=True, content=content)

    def read(self, run_id: str, arguments: WebReadResultInput) -> ToolResult:
        if getattr(self.provider, "configured", True) is False:
            return ToolResult(ok=False, error_code="search_provider_unconfigured")
        try:
            state = self.store.load(run_id)
            record = next(
                (item for item in state.records if item.query_id == arguments.query_id), None
            )
            hit = (
                next((item for item in record.hits if item.result_id == arguments.result_id), None)
                if record is not None
                else None
            )
            if hit is None:
                return ToolResult(ok=False, error_code="source_unavailable")
            if state.reads >= _MAX_READS or state.output_bytes >= _MAX_TOTAL_BYTES:
                return ToolResult(ok=False, error_code="quota_exceeded")
            self.store.save(run_id, state.model_copy(update={"reads": state.reads + 1}))
            raw = self.provider.extract(hit.canonical_url)
        except (ResearchStoreError, WebResearchProviderError) as exc:
            return ToolResult(ok=False, error_code=str(exc))
        excerpt, truncated = _bounded_text(
            raw, min(_MAX_EXCERPT_BYTES, _MAX_TOTAL_BYTES - state.output_bytes)
        )
        if not excerpt:
            return ToolResult(ok=False, error_code="source_unavailable")
        content: dict[str, object] = {
            "query_id": arguments.query_id,
            "result_id": hit.result_id,
            "source_id": hit.source_id,
            "canonical_url": hit.canonical_url,
            "title": hit.title,
            "published_at": hit.published_at,
            "fetched_at": datetime.now(UTC).isoformat(),
            "provider_id": self.provider.provider_id,
            "source_type": "unverified",
            "evidence_level": "page_excerpt",
            "excerpt": excerpt,
        }
        byte_count = len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
        if state.output_bytes + byte_count > _MAX_TOTAL_BYTES:
            return ToolResult(ok=False, error_code="quota_exceeded")
        try:
            self.store.save(
                run_id,
                state.model_copy(
                    update={
                        "reads": state.reads + 1,
                        "output_bytes": state.output_bytes + byte_count,
                    }
                ),
            )
        except ResearchStoreError as exc:
            return ToolResult(ok=False, error_code=str(exc))
        return ToolResult(ok=True, content=content, truncated=truncated)

    def result_url(self, run_id: str, arguments: WebReadResultInput) -> str | None:
        try:
            state = self.store.load(run_id)
        except ResearchStoreError:
            return None
        for record in state.records:
            if record.query_id == arguments.query_id:
                for hit in record.hits:
                    if hit.result_id == arguments.result_id:
                        return hit.canonical_url
        return None
