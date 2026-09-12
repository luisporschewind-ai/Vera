"""Deterministic read-only review projection. Never calls a provider."""

from __future__ import annotations

from typing import Any

from vera.contracts.events import EventEnvelope


def project_review(events: tuple[EventEnvelope, ...]) -> dict[str, Any]:
    files: list[str] = []
    risks: list[str] = []
    approvals: list[str] = []
    verifications: list[dict[str, Any]] = []
    side_effects = False
    for event in events:
        if event.type == "changeset.proposed":
            payload_files = event.payload.get("files", [])
            if isinstance(payload_files, list):
                for item in payload_files:
                    if isinstance(item, dict):
                        path = item.get("path")
                        if isinstance(path, str) and path not in files:
                            files.append(path)
            risk = event.payload.get("risk")
            if isinstance(risk, str) and risk:
                risks.append(risk)
        elif event.type == "approval.required":
            kind = event.payload.get("kind")
            risk = event.payload.get("risk")
            approvals.append(f"{kind}:{risk}")
        elif event.type == "verification.completed":
            verifications.append(
                {
                    "status": event.payload.get("status"),
                    "exit_code": event.payload.get("exit_code"),
                }
            )
        elif event.type in {"changeset.applied", "command.finished"}:
            side_effects = True
    return {
        "files": files,
        "risks": risks,
        "approvals": approvals,
        "verifications": verifications,
        "side_effects": side_effects,
        "empty": not events,
    }
