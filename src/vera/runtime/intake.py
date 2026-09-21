"""Runtime input models and pure target/nudge helpers."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from vera.contracts.events import EventEnvelope
from vera.contracts.verification import VerificationCommand
from vera.models.base import ModelToolCall
from vera.workspace.changeset import ChangeProposal

_TOOL_LIMIT_WRAP_UP = (
    "工具调用次数已达本次任务上限。请只根据已经收集到的证据给出结论，不要再调用任何工具。"
)
_TOOL_LIMIT_SKIPPED = (
    '{"content_hash":"","notice":"skipped: tool call budget exhausted","vera_content":1}'
)
_EMPTY_AFTER_TOOLS_NUDGE = (
    "上一次回复没有文本也没有工具调用。请根据已经收集到的证据给出最终中文回答，"
    "或调用 propose_changeset；不要返回空响应。"
)
_CLAIMED_CHANGESET_NUDGE = (
    "你还没有调用 propose_changeset。只有该工具才会出现审批卡和 Diff；"
    "不要声称已经形成 Change Set 或正在等待审批。"
    "若要改文件，现在就调用 propose_changeset；否则只说明结论，不要假装变更已提交。"
)
_CLAIMED_CHANGESET_MARKERS = (
    "已形成 change set",
    "已形成 changeset",
    "等待你审批",
    "等待审批",
)


def claims_unissued_changeset(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in _CLAIMED_CHANGESET_MARKERS)


def tool_call_target(call: ModelToolCall) -> str:
    arguments = call.arguments if isinstance(call.arguments, dict) else {}
    if call.name == "propose_changeset":
        summary = arguments.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        changes = arguments.get("changes")
        if isinstance(changes, list) and changes:
            first = changes[0]
            if isinstance(first, dict) and first.get("path"):
                extra = f" 等{len(changes)}个文件" if len(changes) > 1 else ""
                return f"{first['path']}{extra}"
        return ""
    path = arguments.get("path")
    query = arguments.get("query")
    if call.name == "search_text" and isinstance(query, str) and query:
        if isinstance(path, str) and path and path != ".":
            return f"{query} @ {path}"
        return query
    if isinstance(path, str) and path:
        return path
    return ""


class SnapshotPersistError(RuntimeError):
    """Raised after a failed snapshot write so the Runtime can stop without looping."""

    def __init__(self, failed_event: EventEnvelope) -> None:
        super().__init__("snapshot_write_failed")
        self.failed_event = failed_event


class ProposalInput(BaseModel):
    summary: str
    changes: tuple[ChangeProposal, ...]
    verification: tuple[VerificationCommand, ...] = ()
    risk: str = "medium"

    @field_validator("verification", mode="before")
    @classmethod
    def ignore_model_artifact_plan(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        cleaned: list[object] = []
        for item in value:
            if isinstance(item, dict):
                payload = dict(item)
                payload.pop("artifact_plan", None)
                cleaned.append(payload)
            elif isinstance(item, VerificationCommand):
                cleaned.append(item.model_copy(update={"artifact_plan": None}))
            else:
                cleaned.append(item)
        return cleaned


__all__ = [
    "ProposalInput",
    "SnapshotPersistError",
    "_CLAIMED_CHANGESET_NUDGE",
    "_EMPTY_AFTER_TOOLS_NUDGE",
    "_TOOL_LIMIT_SKIPPED",
    "_TOOL_LIMIT_WRAP_UP",
    "claims_unissued_changeset",
    "tool_call_target",
]
