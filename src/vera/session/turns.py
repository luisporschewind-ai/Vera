"""Pure conversation-turn projection from stable terminal events."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Sequence

from vera.contracts.events import EventEnvelope
from vera.contracts.sessions import ConversationTurn, TerminalState
from vera.redaction import Redactor


def _execution_facts(events: Sequence[EventEnvelope]) -> str:
    """Bounded historical evidence, never permission or executable instructions."""
    fields = {
        "approval.required": ("approval_id", "kind", "tool_name", "action_id"),
        "approval.resolved": ("approval_id", "kind", "decision"),
        "tool.completed": ("call_id", "name", "ok", "error_code", "target", "content_hash"),
    }
    rows: deque[str] = deque(maxlen=16)
    for event in events:
        keys = fields.get(event.type)
        if keys is None:
            continue
        fact: dict[str, object] = {
            "source": "core_event_history",
            "historical_only": True,
            "run_id": event.run_id,
            "event_id": event.event_id,
            "type": event.type,
        }
        for key in keys:
            value = event.payload.get(key)
            if isinstance(value, str):
                fact[key] = value[:256]
                if len(value) > 256:
                    fact["fields_truncated"] = True
            elif isinstance(value, bool):
                fact[key] = value
        grant = event.payload.get("file_access")
        if event.type == "tool.completed" and isinstance(grant, dict):
            for key in ("grant_id", "path", "mode", "scope", "recursive"):
                value = grant.get(key)
                if isinstance(value, str):
                    fact[key] = value[:256]
                    if len(value) > 256:
                        fact["fields_truncated"] = True
                elif isinstance(value, bool):
                    fact[key] = value
        rows.append(
            "[facts] "
            + json.dumps(
                Redactor().redact(fact),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    while rows and len("\n".join(rows).encode("utf-8")) > 8000:
        rows.popleft()
    return "\n".join(rows)


_RECOVERY_TYPES = frozenset(
    {
        "recovery.detected",
        "recovery.manual_required",
        "recovery.abandoned",
    }
)


class ConversationTurnProjector:
    def from_response(self, user_text: str, assistant_text: str) -> ConversationTurn:
        return ConversationTurn(
            user_text=user_text,
            assistant_text=assistant_text,
            run_id=None,
            terminal_state="response",
        )

    def from_run(self, user_text: str, events: Sequence[EventEnvelope]) -> ConversationTurn:
        assistant_text = self._assistant_from_events(events)
        summary = self._summary_from_events(events)
        has_changeset = any(event.type == "changeset.proposed" for event in events)
        if assistant_text is not None and not has_changeset:
            body = assistant_text
        else:
            body = summary
            if assistant_text is not None and assistant_text not in summary:
                body = f"{assistant_text}\n{summary}"
        if not body.strip():
            body = summary or "run 已结束。"
        execution_facts = _execution_facts(events)
        if execution_facts:
            body = f"{body}\n{execution_facts}"
        return ConversationTurn(
            user_text=user_text,
            assistant_text=body,
            run_id=events[0].run_id if events else None,
            terminal_state=self._terminal_state(events, has_changeset=has_changeset),
        )

    @staticmethod
    def _terminal_state(events: Sequence[EventEnvelope], *, has_changeset: bool) -> TerminalState:
        types = {event.type for event in events}
        if "run.cancelled" in types:
            return "cancelled"
        if "run.failed" in types:
            return "failed"
        if types & _RECOVERY_TYPES or "rollback.conflicted" in types:
            return "recovery"
        if (
            "run.completed" in types
            and not has_changeset
            and any(
                event.type == "assistant.message"
                and isinstance(event.payload.get("content"), str)
                and str(event.payload.get("content", "")).strip()
                for event in events
            )
        ):
            return "response"
        if "run.completed" in types or "rollback.completed" in types:
            return "completed"
        return "response"

    @staticmethod
    def _assistant_from_events(events: Sequence[EventEnvelope]) -> str | None:
        for event in reversed(events):
            if event.type != "assistant.message":
                continue
            content = event.payload.get("content")
            if isinstance(content, str) and content.strip():
                return content
        return None

    @staticmethod
    def _fact_block(events: Sequence[EventEnvelope]) -> str:
        run_id = events[0].run_id if events else "unknown"
        parts = [f"run={run_id}"]
        for event in events:
            if event.type == "changeset.proposed":
                changeset_id = event.payload.get("changeset_id", "")
                files = event.payload.get("files") or []
                file_parts: list[str] = []
                if isinstance(files, list):
                    for item in files:
                        if not isinstance(item, dict):
                            continue
                        file_parts.append(f"{item.get('operation')} {item.get('path')}")
                parts.append(f"changeset={changeset_id} files={'; '.join(file_parts)}")
            elif event.type == "approval.required":
                parts.append(f"approval={event.payload.get('approval_id')}")
            elif event.type == "run.failed":
                parts.append(f"error={event.payload.get('reason')}")
            elif event.type in _RECOVERY_TYPES:
                parts.append(f"recovery={event.payload.get('classification')}")
        if parts == [f"run={run_id}"]:
            return ""
        return "[facts] " + " ".join(str(part) for part in parts)

    @classmethod
    def _summary_from_events(cls, events: Sequence[EventEnvelope]) -> str:
        run_id = events[0].run_id if events else "unknown"
        human = f"run {run_id} 已结束。"
        for event in events:
            if event.type == "run.cancelled":
                human = f"run {run_id} 已取消，工作区未应用该 Change Set。"
                break
            if event.type == "run.failed":
                reason = event.payload.get("reason", "unknown")
                human = f"run {run_id} 失败：{reason}。"
                break
            if event.type == "recovery.manual_required":
                human = f"run {run_id} 需要人工恢复。"
                break
            if event.type == "recovery.abandoned":
                human = f"run {run_id} 已放弃恢复。"
                break
            if event.type == "run.completed":
                if any(item.type == "changeset.applied" for item in events):
                    human = f"run {run_id} 已应用 Change Set，验证通过。"
                else:
                    outcome = event.payload.get("outcome", "completed")
                    human = f"run {run_id} 已完成（{outcome}）。"
                break
        facts = cls._fact_block(events)
        if facts:
            return f"{human}\n{facts}"
        return human
