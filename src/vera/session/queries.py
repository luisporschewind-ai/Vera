"""Read-only session queries over persisted run facts."""

from __future__ import annotations

from typing import Any

from vera.contracts.events import EventEnvelope
from vera.persistence.run_store import RunStore


def resolve_run_id(store: RunStore, requested: str | None, fallback: str | None) -> str | None:
    if requested:
        return requested
    if fallback:
        return fallback
    runs = store.list_runs()
    return runs[0].run_id if runs else None


def collect_diffs(events: tuple[EventEnvelope, ...]) -> tuple[dict[str, Any], ...]:
    files: list[dict[str, Any]] = []
    for event in events:
        if event.type != "changeset.proposed":
            continue
        payload_files = event.payload.get("files", [])
        if not isinstance(payload_files, list):
            continue
        for item in payload_files:
            if isinstance(item, dict):
                files.append(dict(item))
    return tuple(files)


def load_run_events(store: RunStore, run_id: str) -> tuple[EventEnvelope, ...]:
    return tuple(store.read_events(run_id))


def usage_snapshot(events: tuple[EventEnvelope, ...]) -> dict[str, object]:
    cache_unavailable: dict[str, object] = {
        "cache_hit_input_tokens": "unavailable",
        "cache_miss_input_tokens": "unavailable",
        "cache_hit_percent": "unavailable",
    }
    completed = [event for event in events if event.type == "model.completed"]
    if not completed:
        return {
            "calls": "unavailable",
            "input_tokens": "unavailable",
            "output_tokens": "unavailable",
            "total_tokens": "unavailable",
            **cache_unavailable,
        }
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    cache_hits = 0
    cache_misses = 0
    cache_valid = True
    for event in completed:
        payload = event.payload.get("usage")
        if not isinstance(payload, dict):
            return {
                "calls": "unavailable",
                "input_tokens": "unavailable",
                "output_tokens": "unavailable",
                "total_tokens": "unavailable",
                **cache_unavailable,
            }
        for field in totals:
            value = payload.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return {
                    "calls": "unavailable",
                    "input_tokens": "unavailable",
                    "output_tokens": "unavailable",
                    "total_tokens": "unavailable",
                    **cache_unavailable,
                }
            totals[field] += value
        hit = payload.get("cache_hit_input_tokens")
        miss = payload.get("cache_miss_input_tokens")
        if (
            type(hit) is not int
            or type(miss) is not int
            or hit < 0
            or miss < 0
            or hit + miss != payload["input_tokens"]
        ):
            cache_valid = False
        else:
            cache_hits += hit
            cache_misses += miss
    result: dict[str, object] = {
        "calls": len(completed),
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "total_tokens": totals["total_tokens"],
    }
    if cache_valid:
        result.update(
            {
                "cache_hit_input_tokens": cache_hits,
                "cache_miss_input_tokens": cache_misses,
                "cache_hit_percent": (
                    round(100 * cache_hits / totals["input_tokens"], 1)
                    if totals["input_tokens"]
                    else "unavailable"
                ),
            }
        )
    else:
        result.update(cache_unavailable)
    return result
