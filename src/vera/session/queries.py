"""Read-only session queries over persisted run facts."""

from __future__ import annotations

from typing import Any

from vera.contracts.events import EventEnvelope
from vera.persistence.run_store import RunStore


def resolve_run_id(store: RunStore, requested: str | None, fallback: str | None) -> str | None:
    if requested:
        return requested
    return fallback


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
    completed = [event for event in events if event.type == "model.completed"]
    if not completed:
        return {
            "calls": "unavailable",
            "input_tokens": "unavailable",
            "output_tokens": "unavailable",
            "total_tokens": "unavailable",
        }
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for event in completed:
        payload = event.payload.get("usage")
        if not isinstance(payload, dict):
            return {
                "calls": "unavailable",
                "input_tokens": "unavailable",
                "output_tokens": "unavailable",
                "total_tokens": "unavailable",
            }
        for field in totals:
            value = payload.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return {
                    "calls": "unavailable",
                    "input_tokens": "unavailable",
                    "output_tokens": "unavailable",
                    "total_tokens": "unavailable",
                }
            totals[field] += value
    return {
        "calls": len(completed),
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "total_tokens": totals["total_tokens"],
    }
